import streamlit as st
import requests
import json
import re
import io
from io import BytesIO
import zipfile

# Add this near the top of your app, after the imports
st.set_page_config(page_title="Seedling Converter")

def query_chatgpt_api(message: str, conversation_history: list = None) -> tuple[str, dict, str]:
    """
    Calls OpenAI's Chat Completion API (ChatGPT) with conversation history support.
    Returns a tuple of (response_content, token_usage, raw_response).

    This function first attempts to use Streamlit's secrets (st.secrets) for the API key.
    """
    
    
    api_key = st.secrets.get("OPENAI_API_KEY")
    if not api_key:
        return "Error: No OPENAI_API_KEY available.", {}, ""

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    
    messages = conversation_history[:] if conversation_history else []
    messages.append({"role": "user", "content": message})
    
    payload = {"model": "o1-mini", "messages": messages, "max_completion_tokens": 20000}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=240)
        response.raise_for_status()
        response_data = response.json()
        raw_response = json.dumps(response_data, indent=2)
        if "choices" in response_data and response_data["choices"]:
            content = response_data["choices"][0]["message"]["content"]
            token_usage = response_data.get("usage", {})
            if conversation_history is not None:
                conversation_history.append({"role": "assistant", "content": content})
            return content, token_usage, raw_response
        return "Could not extract content from ChatGPT response.", {}, raw_response
    except requests.exceptions.RequestException as e:
        error_message = f"API request failed: {str(e)}"
        if hasattr(e, "response") and e.response is not None:
            error_message += f"\nResponse: {e.response.text}"
            raw_error = e.response.text
        else:
            raw_error = str(e)
        return error_message, {}, raw_error
    except Exception as e:
        return f"Unexpected error: {str(e)}", {}, str(e)

# =============================================================================
# File Conversion Functions
# =============================================================================
def convert_file_name(original_name: str, target_extension: str) -> str:
    """
    Given an original file name (e.g. 'aa2tjhd6kio-txt') and a target extension (e.g. 'txt'),
    returns the new file name (e.g. 'aa2tjhd6kio.txt').
    
    If the file name contains a hyphen, this function splits on the last hyphen.
    Otherwise, if a dot exists, it replaces the extension; else it appends the target extension.
    """
    if '-' in original_name:
        base, _ = original_name.rsplit('-', 1)
    elif '.' in original_name:
        base, _ = original_name.rsplit('.', 1)
    else:
        base = original_name
    new_filename = f"{base}.{target_extension}"
    return new_filename

def convert_uploaded_file(uploaded_file, target_extension: str) -> tuple[str, bytes]:
    """
    Takes a Streamlit UploadedFile object and a target extension.
    Returns a tuple of (new_file_name, file_bytes). The conversion here is just a renaming.
    """
    original_name = uploaded_file.name
    new_filename = convert_file_name(original_name, target_extension)
    file_bytes = uploaded_file.getvalue()
    return new_filename, file_bytes

# =============================================================================
# ChatGPT Response Parsing
# =============================================================================
def parse_chatgpt_response(response_text: str, uploaded_filenames: list) -> tuple[dict, str]:
    """
    Expects a response where each non-empty line is in the format:
      <file_name>, <target_extension>
    
    Returns a dictionary mapping the original file name to the target extension,
    or an error string (non-empty) if something is wrong.
    """
    mapping = {}
    # Remove code block markers if present
    response_text = response_text.strip('`')
    lines = response_text.strip().splitlines()
    if not lines:
        return None, "Empty response from ChatGPT."
    
    for line in lines:
        # Ignore empty lines and code block markers
        if not line.strip() or line.strip() == '```':
            continue
        parts = line.split(',')
        if len(parts) != 2:
            return None, f"Invalid format in line: {line}"
        file_name = parts[0].strip()
        target_ext = parts[1].strip().lower()
        if target_ext not in ['jpeg', 'png', 'txt', 'pdf', 'docx']:
            return None, f"Unsupported file type '{target_ext}' for file '{file_name}'."
        mapping[file_name] = target_ext

    # Ensure every uploaded file is in the mapping.
    for fname in uploaded_filenames:
        if fname not in mapping:
            return None, f"File '{fname}' is missing in ChatGPT response."
    return mapping, ""

# =============================================================================
# Streamlit App
# =============================================================================
# Custom CSS for the layout
st.markdown("""
    <style>
        .main-container {
            display: flex;
            flex-direction: row;
        }
        .logo-container {
            width: 300px;
            padding: 20px;
            position: fixed;
            left: 0;
            top: 0;
        }
        .content-container {
            margin-left: 320px;
            flex-grow: 1;
            padding: 20px;
        }
    </style>
""", unsafe_allow_html=True)

# Main container with logo and content
st.markdown('<div class="main-container">', unsafe_allow_html=True)

# Logo container
st.markdown('<div class="logo-container">', unsafe_allow_html=True)
st.image("images/orchard_logo.png", width=280)
st.markdown('</div>', unsafe_allow_html=True)

# Content container
st.markdown('<div class="content-container">', unsafe_allow_html=True)

# Title
st.markdown("""
<h1>
    <span style='color: #2E7D32; font-weight: bold;'>Seedling</span>: 
    Orchard's File Converter
</h1>
""", unsafe_allow_html=True)

# Description
st.write("""
This app accepts multiple file uploads (drag & drop supported), sends the file list to ChatGPT to determine 
the correct file type (among **jpeg**, **png**, **txt**, or **pdf**), and then renames each file accordingly.
After conversion, you will get a download link for each file.

---
**Supported File Types:**
- JPEG Images (.jpeg)
- PNG Images (.png)
- Text Files (.txt)
- PDF Documents (.pdf)
- Word Documents (.docx)
""")

# Debug mode toggle
st.checkbox("Debug Mode", key="debug_mode", value=st.session_state.get('debug_mode', False))

# Add after line 196
if 'debug_mode' not in st.session_state:
    st.session_state.debug_mode = False

# File uploader
uploaded_files = st.file_uploader("Upload your files", accept_multiple_files=True)

# Add after line 190
if uploaded_files is None:  # This means the uploader is waiting
    st.info("Waiting for files to be uploaded...")

st.markdown('</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# Add this near the top of the file, after the imports
if 'processed_files' not in st.session_state:
    st.session_state.processed_files = []
    st.session_state.selected_files = set()

if 'upload_page' not in st.session_state:
    st.session_state.upload_page = 0
if 'process_page' not in st.session_state:
    st.session_state.process_page = 0

ITEMS_PER_PAGE = 10

if uploaded_files:
    st.subheader("Uploaded Files:")
    
    # Add check/uncheck all buttons in columns
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Check All"):
            st.session_state.selected_files = set(f.name for f in uploaded_files)
    with col2:
        if st.button("Uncheck All"):
            st.session_state.selected_files = set()
    
    # Pagination for uploaded files
    total_files = len(uploaded_files)
    total_pages = (total_files + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    
    start_idx = st.session_state.upload_page * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, total_files)
    
    # Display checkboxes for current page
    for f in uploaded_files[start_idx:end_idx]:
        is_checked = st.checkbox(f"Process {f.name}", 
                               key=f"checkbox_{f.name}",
                               value=f.name in st.session_state.selected_files)
        if is_checked:
            st.session_state.selected_files.add(f.name)
        else:
            st.session_state.selected_files.discard(f.name)
    
    # Pagination controls
    if total_pages > 1:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            if st.button("Previous", key="prev_upload", disabled=st.session_state.upload_page == 0):
                st.session_state.upload_page = max(0, st.session_state.upload_page - 1)
                st.rerun()
        with col2:
            st.write(f"Page {st.session_state.upload_page + 1} of {total_pages}")
        with col3:
            if st.button("Next", key="next_upload", disabled=st.session_state.upload_page >= total_pages - 1):
                st.session_state.upload_page = min(total_pages - 1, st.session_state.upload_page + 1)
                st.rerun()

    def process_selected_files():
        # Only process checked files
        selected_files = [f for f in uploaded_files if f.name in st.session_state.selected_files]
        if not selected_files:
            st.warning("Please select at least one file to process.")
            return
            
        # Step 1. Prepare the list of file names.
        uploaded_filenames = [f.name for f in selected_files]
        
        # Step 2. Create the prompt for ChatGPT.
        prompt = (
            "I have the following list of file names. For each file, determine the correct file extension "
            "that it should have. Only use one of the following extensions: jpeg, png, txt, pdf, docx. "
            "Return exactly one line per file in the format:\n"
            "<file_name>, <target_extension>\n\n"
            "Do not include any additional text or explanations.\n\n"
            "Here is the list of files:\n" + "\n".join(uploaded_filenames)
        )
        st.info("Sending file list to ChatGPT for conversion assignment...")
        response, usage, raw = query_chatgpt_api(prompt)
        
        # Only show ChatGPT output if debug mode is enabled
        if st.session_state.debug_mode:
            st.write("**ChatGPT Raw Response:**")
            st.code(response, language="text")
            st.write("**Token Usage:**")
            st.json(usage)

        # Step 3. Parse and validate ChatGPT's response.
        mapping, error = parse_chatgpt_response(response, uploaded_filenames)
        if error:
            st.error(f"Error parsing ChatGPT response: {error}")
            return

        if not st.session_state.debug_mode:
            st.success("Files processed successfully!")
        else:
            st.success("ChatGPT response parsed successfully. File conversion mapping:")
            st.json(mapping)

        # Process files first
        for f in selected_files:
            target_ext = mapping.get(f.name)
            if not target_ext:
                st.error(f"No target extension for file {f.name}. Skipping.")
                continue
                
            new_filename, file_bytes = convert_uploaded_file(f, target_ext)
            
            # Store processed file info
            st.session_state.processed_files.append({
                'filename': new_filename,
                'bytes': file_bytes
            })

    if st.button("Process Files"):
        process_selected_files()

    # Display processed files section (outside the process_selected_files function)
    if st.session_state.processed_files:
        st.subheader("Converted Files:")
        
        # Pagination for processed files
        total_processed = len(st.session_state.processed_files)
        total_proc_pages = (total_processed + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        
        start_idx = st.session_state.process_page * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, total_processed)
        
        # Display current page of processed files
        for file_info in st.session_state.processed_files[start_idx:end_idx]:
            st.write(f"**{file_info['filename']}**")
            
            # Individual download button
            st.download_button(
                label=f"Download {file_info['filename']}",
                data=file_info['bytes'],
                file_name=file_info['filename'],
                mime="application/octet-stream",
                key=f"download_{file_info['filename']}"
            )
        
        # Pagination controls for processed files
        if total_proc_pages > 1:
            col1, col2, col3 = st.columns([1, 2, 1])
            with col1:
                if st.button("Previous", key="prev_proc", disabled=st.session_state.process_page == 0):
                    st.session_state.process_page = max(0, st.session_state.process_page - 1)
                    st.rerun()
            with col2:
                st.write(f"Page {st.session_state.process_page + 1} of {total_proc_pages}")
            with col3:
                if st.button("Next", key="next_proc", disabled=st.session_state.process_page >= total_proc_pages - 1):
                    st.session_state.process_page = min(total_proc_pages - 1, st.session_state.process_page + 1)
                    st.rerun()

        # Add download all button
        if st.session_state.processed_files:
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                def create_zip():
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for file_info in st.session_state.processed_files:
                            zip_file.writestr(file_info['filename'], file_info['bytes'])
                    return zip_buffer.getvalue()

                st.download_button(
                    label="Download All Files (ZIP)",
                    data=create_zip(),
                    file_name="converted_files.zip",
                    mime="application/zip",
                    key="download_all"
                )
