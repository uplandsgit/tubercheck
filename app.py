import os
from flask import Flask, render_template, request, redirect, url_for, jsonify
from google import genai
from PIL import Image
import io
import re # <-- New: Added import for regex

# Initialize Flask App
app = Flask(__name__)

# --- Gemini Configuration ---
try:
    # Client Initialization. Vercel automatically finds the GEMINI_API_KEY environment variable.
    client = genai.Client()
except Exception as e:
    print(f"Error initializing Gemini client: {e}")
    client = None

# --- Gemini Prompt ---
GALL_ANALYSIS_PROMPT = """
Analyze the attached image(s) of a dahlia tuber. Act as a certified plant pathology expert.

1.  **Identify Growths:** Determine if there are any abnormal growths, tumors, or distorted tissue present, specifically looking for Crown Gall (Agrobacterium tumefaciens).
2.  **Describe Findings:** Describe the visual evidence found. If no gall is present, describe the healthy appearance.
3.  **Provide a Verdict:** Give a clear, concise final verdict.

Crucially, format your final verdict on a single line using ONLY this exact structure: [VERDICT: Gall Present / Gall Not Present] [CONFIDENCE: X%]
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
        # FIX: Removed 'timeout=25' argument to fix the TypeError.
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=content
        )
        analysis_text = response.text
        
        # --- START RESPONSE CLEANUP (New Logic) ---
        # 1. Remove the bold HTML tags (the Jinja filter in results.html handles bolding)
        analysis_text = analysis_text.replace('<strong>', '').replace('</strong>', '')

        # 2. Remove the structured headers/numbers/bolding from the prompt response
        # This targets patterns like "1. **Identify Growths:** "
        analysis_text = re.sub(r'^\d+\.\s+\*\*.*?\*\*:\s*', '', analysis_text, flags=re.MULTILINE)

        # 3. Collapse all multiple spaces and newlines into a single clean paragraph, 
        # then re-introduce a newline before the verdict for neat separation.
        analysis_text = analysis_text.replace('\n', ' ').strip()
        analysis_text = re.sub(r'\s+', ' ', analysis_text).strip()
        analysis_text = analysis_text.replace('[VERDICT', '\n[VERDICT')
        # --- END RESPONSE CLEANUP ---

        # --- 3. Redirect to the results page ---
        return redirect(url_for('results', analysis=analysis_text))
        
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