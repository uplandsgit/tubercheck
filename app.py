import os
from flask import Flask, render_template, request, redirect, url_for, jsonify
from google import genai
from PIL import Image
import io

# Initialize Flask App
app = Flask(__name__)

# --- Gemini Configuration ---
# The client will automatically pick up the GEMINI_API_KEY from Vercel's environment variables.
# We include this definition block to ensure the 'client' variable is defined globally.
try:
    client = genai.Client()
except Exception as e:
    print(f"Error initializing Gemini client: {e}")
    client = None

# --- Gemini Prompt ---
# The instructions for the model, forcing the required output format.
GALL_ANALYSIS_PROMPT = """
Analyze the attached image(s) of a dahlia tuber. Act as a certified plant pathology expert.

1.  **Identify Growths:** Determine if there are any abnormal growths, tumors, or distorted tissue present, specifically looking for Crown Gall (Agrobacterium tumefaciens).
2.  **Describe Findings:** Describe the visual evidence found. If no gall is present, describe the healthy appearance.
3.  **Provide a Verdict:** Give a clear, concise final verdict.

Crucially, format your final verdict on a single line using ONLY this exact structure: [VERDICT: Gall Present / Gall Not Present] [CONFIDENCE: X%]
"""
# -----------------------------

@app.route('/')
def index():
    """
    Renders the main upload page (index.html). 
    This is what the user sees when they first visit the site.
    """
    # FIX: Render index.html (the upload form) and do not use the undefined 'analysis_text'
    return render_template('index.html')


@app.route('/analyze', methods=['POST'])
def analyze_tuber():
    """
    Handles the image upload, calls the Gemini API for analysis, 
    and redirects to the results page upon completion.
    """
    if not client:
        # In a production setup, this would return an error page, but we'll use a redirect for simplicity.
        return redirect(url_for('results', analysis="ERROR: AI service not configured. Check GEMINI_API_KEY."))
    
    if 'photos' not in request.files:
        # Redirect back to the form if no files were selected
        return redirect(url_for('index'))

    uploaded_files = request.files.getlist('photos')
    
    # --- 1. Prepare Content for Gemini API ---
    content = [GALL_ANALYSIS_PROMPT]
    
    for file in uploaded_files:
        if file.filename != '':
            try:
                # Read file content into memory and open as a PIL Image
                img = Image.open(io.BytesIO(file.read()))
                content.append(img)
            except Exception as e:
                # Log non-image file errors and skip
                print(f"Skipping non-image file: {file.filename} Error: {e}")
                continue

    if len(content) == 1: # Only the prompt, no images
        # Redirect back to the form if no valid images were submitted
        return redirect(url_for('index'))
        
    # --- 2. Call the Gemini API ---
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=content
        )
        analysis_text = response.text
        
        # --- 3. Redirect to the results page ---
        # We redirect and pass the result as a URL parameter (using a session/database would be better 
        # for very long text, but query parameter works for now).
        return redirect(url_for('results', analysis=analysis_text))
        
    except Exception as e:
        error_message = f"Gemini API Error: {e}"
        print(error_message)
        return redirect(url_for('results', analysis=error_message))


@app.route('/results')
def results():
    """
    Renders the results.html page using the analysis text passed via the query parameter.
    """
    # Get the analysis text from the URL query parameter 'analysis'
    analysis_text = request.args.get('analysis', "No analysis found.")
    
    # FIX: Render results.html, using the text from the URL parameter
    return render_template('results.html', result=analysis_text)


if __name__ == '__main__':
    # When testing locally, you need to set your GEMINI_API_KEY in your environment
    app.run(debug=True)