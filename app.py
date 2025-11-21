from flask import Flask, render_template, request, redirect, url_for
from google import genai
from PIL import Image
import io
import re

# Initialize Flask App
app = Flask(__name__)

# --- Gemini Configuration ---
try:
    # Client Initialization. Vercel automatically finds the GEMINI_API_KEY environment variable.
    client = genai.Client()
except Exception as e:
    print(f"Error initializing Gemini client: {e}")
    client = None

# --- Gemini Prompt (Updated to look for both Crown Gall and Leafy Gall) ---
GALL_ANALYSIS_PROMPT = """
Analyze the attached image(s) of a dahlia tuber. Act as a certified plant pathology expert. 
Your response must consist only of the analysis and the final verdict line.

**Identify Growths:** Determine if there are any abnormal growths, tumors, or distorted tissue present, specifically looking for signs of Crown Gall (Agrobacterium tumefaciens) and Leafy Gall (Rhodococcus fascians).
**Describe Findings:** Describe the visual evidence found, noting if the growths are hard and tumor-like (Crown Gall) or bushy and distorted (Leafy Gall). If no gall is present, describe the healthy appearance.

Crucially, format your final verdict on a single line using ONLY this exact structure: [VERDICT: Gall Disease Present / Gall Disease Not Present] [CONFIDENCE: X%]
"""
# -----------------------------

def optimize_image(image: Image.Image) -> Image.Image:
    """Resizes and compresses the image to prevent memory and timeout issues on Vercel."""
    MAX_SIZE = (1024, 1024) # Maximum resolution
    
    # Resize the image if necessary
    if image.width > MAX_SIZE[0] or image.height > MAX_SIZE[1]:
        # Use LANCZOS for high-quality downsampling
        image.thumbnail(MAX_SIZE, Image.Resampling.LANCZOS)
    
    # Convert image format to RGB (JPEG) for predictable compression if needed
    if image.mode in ('RGBA', 'P', 'LA'):
        image = image.convert('RGB')
        
    return image


@app.route('/')
def index():
    """Renders the main upload page (index.html)."""
    return render_template('index.html')


@app.route('/analyze', methods=['POST'])
def analyze_tuber():
    """
    Handles the image upload, optimizes the image, calls the Gemini API, 
    and redirects to the results page.
    """
    # Check 1: AI Service Check
    if not client:
        return redirect(url_for('results', analysis="ERROR: AI service not configured. Check GEMINI_API_KEY environment variable."))
    
    # Check 2: File Upload Check
    if 'photos' not in request.files:
        return redirect(url_for('index'))

    uploaded_files = request.files.getlist('photos')
    
    # --- 1. Prepare Content for Gemini API ---
    content = [GALL_ANALYSIS_PROMPT]
    
    for file in uploaded_files:
        if file.filename != '':
            try:
                # Read file content into memory
                img_stream = io.BytesIO(file.read())
                original_img = Image.open(img_stream)
                
                # CRITICAL IMPROVEMENT: Optimize image size before sending
                optimized_img = optimize_image(original_img)
                content.append(optimized_img)
                
            except Exception as e:
                # Log non-image file errors and skip
                print(f"Skipping non-image file or failed to process: {file.filename}. Error: {e}")
                continue

    if len(content) == 1: # Only the prompt, no images
        return redirect(url_for('index'))
        
    # --- 2. Call the Gemini API ---
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=content
        )
        analysis_text = response.text
        
        # --- START RESPONSE CLEANUP AND FORMATTING ---
        # 1. FIX: Use regex to remove ANY HTML tag (like <strong>, <b>, <em>) from the text.
        analysis_text = re.sub(r'<[^>]+>', '', analysis_text)

        # 2. Extract the verdict line separately.
        # Note: The verdict structure now accommodates "Gall Disease Present / Gall Disease Not Present"
        verdict_match = re.search(r'\[VERDICT:.*?\]\s*\[CONFIDENCE:.*?%\]', analysis_text, re.DOTALL)
        verdict_line = verdict_match.group(0).strip() if verdict_match else "[VERDICT: Error] [CONFIDENCE: 0%]"
        
        # 3. Remove verdict and surrounding newlines from the rest of the text
        clean_analysis = re.sub(r'\[VERDICT:.*?\]\s*\[CONFIDENCE:.*?%\]', '', analysis_text, flags=re.DOTALL).strip()
        
        # 4. Remove the old numbered list markers and headings (1. **, 2. **, 3. **, etc.) - Safeguard
        clean_analysis = re.sub(r'^\d+\.\s+\*\*.*?\*\*:\s*', '', clean_analysis, flags=re.MULTILINE).strip()
        
        # 5. CONVERT BOLDED HEADINGS TO H4 TAGS, but exclude "Provide a Verdict"
        # 5a. Remove the unwanted "Provide a Verdict:" header completely if it appears.
        clean_analysis = re.sub(r'\*\*Provide a Verdict\*\*:\s*', '', clean_analysis, flags=re.MULTILINE).strip()
        
        # 5b. Convert all remaining bolded headers (Identify Growths, Describe Findings) to H4 tags for styling
        clean_analysis = re.sub(r'\*\*(.*?)\*\*:\s*', r'<h4>\1</h4>\n', clean_analysis, flags=re.MULTILINE).strip()
        
        # 6. Use double newlines to separate sections clearly and collapse multiple newlines/spaces
        clean_analysis = re.sub(r'\n+', '\n\n', clean_analysis).strip()
        
        # 7. Combine verdict and cleaned analysis with a unique separator for Jinja to split
        final_result = f"{verdict_line}---SEPARATOR---{clean_analysis}"
        
        # --- END RESPONSE CLEANUP AND FORMATTING ---

        # --- 3. Redirect to the results page ---
        return redirect(url_for('results', analysis=final_result))
        
    except Exception as e:
        # Catch errors during the API call (network, timeout, quota)
        error_message = f"Critical Error during AI Analysis: {type(e).__name__}: {str(e)}. Please check your Gemini API key and usage quota."
        print(error_message)
        # Redirect to the results page showing the specific error
        return redirect(url_for('results', analysis=error_message))


@app.route('/results')
def results():
    """
    Renders the results.html page, displaying analysis or error message.
    """
    # Get the analysis text from the URL query parameter 'analysis'
    analysis_text = request.args.get('analysis', "No analysis found. Please upload an image.")
    
    return render_template('results.html', result=analysis_text)


if __name__ == '__main__':
    # For local testing
    app.run(debug=True)