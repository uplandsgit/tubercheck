import os
import io
from flask import Flask, request, jsonify, render_template
from google import genai
from PIL import Image

app = Flask(__name__)

# --- Gemini Configuration ---
# The client will automatically pick up the GEMINI_API_KEY environment variable set in Vercel.
try:
    # Ensure the API client initializes correctly
    client = genai.Client()
except Exception as e:
    # This prevents the app from crashing entirely if the key is missing during local test
    print(f"Warning: Gemini client failed to initialize: {e}")
    client = None

# --- AI Prompt for Analysis ---
GALL_ANALYSIS_PROMPT = """
Analyze the attached image(s) of a dahlia tuber. Act as a certified plant pathology expert.

1.  **Identify Growths:** Determine if there are any abnormal growths, tumors, or distorted tissue present.
2.  **Compare to Gall Types:**
    * **Crown Gall:** Look for irregular, woody, tumor-like, swollen masses of disorganized tissue, often near the crown.
    * **Leafy Gall:** Look for dense, distorted, cauliflower-like masses of tiny, fused, and stumpy shoots, typically at the crown or eyes.
    * **Lenticels:** Note if the growths appear to be natural, uniform, puffy lenticels (gas exchange pores) that are often white and scattered.
3.  **Provide a Verdict:** Give a clear, concise verdict based on your analysis.

**Format your response as a single block of text containing the Verdict, Reasoning, and Recommendation, separated by newlines.**
"""

@app.route('/')
def index():
    """Renders the main upload page."""
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze_tuber():
    """Handles the image upload and calls the Gemini API for analysis."""

    if not client:
        return jsonify({"error": "AI service not configured. Check GEMINI_API_KEY."}), 500
    
    if 'photos' not in request.files:
        return jsonify({"error": "No files part in the request"}), 400

    uploaded_files = request.files.getlist('photos')
    
    # --- 1. Prepare Content for Gemini API ---
    content = [GALL_ANALYSIS_PROMPT]
    
    for file in uploaded_files:
        if file.filename != '':
            try:
                # Read file content into memory (BytesIO) for Vercel compatibility
                img = Image.open(io.BytesIO(file.read()))
                content.append(img)
            except Exception as e:
                # Handle non-image files gracefully
                print(f"Skipping non-image file: {file.filename} Error: {e}")
                continue

    if len(content) == 1: # Only the prompt, no images
        return jsonify({"error": "No valid images submitted for analysis."}), 400
        
    # --- 2. Call the Gemini API ---
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=content
        )
        
        # --- 3. Return the Analysis ---
        return jsonify({
            "success": True, 
            "analysis": response.text
        })
        
    except Exception as e:
        return jsonify({"error": f"Gemini API Error: {e}"}), 500

if __name__ == '__main__':
    # When testing locally, you need to set your GEMINI_API_KEY in your environment
    app.run(debug=True)