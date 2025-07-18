import streamlit as st
import openai
import os
from dotenv import load_dotenv
import time
from typing import List, Dict, Any
import config
import uuid
from datetime import datetime

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="AI Assistant Chat",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Apply custom CSS
st.markdown(config.CUSTOM_CSS, unsafe_allow_html=True)

def initialize_session_state():
    """Initialize session state variables"""
    if 'chats' not in st.session_state:
        st.session_state.chats = {}
    if 'current_chat_id' not in st.session_state:
        st.session_state.current_chat_id = None
    if 'client' not in st.session_state:
        st.session_state.client = None
    if 'last_error' not in st.session_state:
        st.session_state.last_error = None
    if 'is_responding' not in st.session_state:
        st.session_state.is_responding = False
    if 'current_message_placeholder' not in st.session_state:
        st.session_state.current_message_placeholder = None

def create_new_chat():
    """Create a new chat session"""
    chat_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%H:%M")
    chat_title = f"New chat {timestamp}"
    
    st.session_state.chats[chat_id] = {
        'id': chat_id,
        'title': chat_title,
        'messages': [],
        'thread_id': None,
        'created_at': datetime.now()
    }
    st.session_state.current_chat_id = chat_id
    return chat_id

def get_current_chat():
    """Get the current chat session"""
    if st.session_state.current_chat_id and st.session_state.current_chat_id in st.session_state.chats:
        return st.session_state.chats[st.session_state.current_chat_id]
    return None

def update_chat_title(chat_id, title):
    """Update the title of a chat"""
    if chat_id in st.session_state.chats:
        st.session_state.chats[chat_id]['title'] = title

def setup_openai_client(api_key: str):
    """Setup OpenAI client with API key"""
    try:
        client = openai.OpenAI(api_key=api_key)
        # Test the connection
        client.models.list()
        return client
    except Exception as e:
        st.error(f"Error connecting to OpenAI: {str(e)}")
        return None

def create_or_get_thread(client, assistant_id: str, chat):
    """Create a new thread or get existing one"""
    try:
        if chat['thread_id'] is None:
            thread = client.beta.threads.create()
            chat['thread_id'] = thread.id
        return chat['thread_id']
    except Exception as e:
        st.error(f"Error creating thread: {str(e)}")
        return None

def send_message(client, thread_id: str, message: str):
    """Send a message to the assistant"""
    try:
        # Cancel any active runs first
        cancel_active_run(client, thread_id)
        
        # Add message to thread
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=message
        )
        
        # Run the assistant
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=config.ASSISTANT_ID,
            instructions=config.ASSISTANT_SYSTEM_PROMPT
        )
        
        return run.id
    except Exception as e:
        st.session_state.last_error = str(e)
        return None

def get_run_status(client, thread_id: str, run_id: str):
    """Get the status of a run and error details if failed"""
    try:
        run = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run_id
        )
        # If failed, store error details
        if run.status == "failed":
            st.session_state.last_error = getattr(run, 'last_error', None) or getattr(run, 'error', None)
        return run.status
    except Exception as e:
        st.session_state.last_error = str(e)
        return None

def cancel_active_run(client, thread_id: str):
    """Cancel any active run in the thread"""
    try:
        runs = client.beta.threads.runs.list(thread_id=thread_id)
        for run in runs.data:
            if run.status in ["queued", "in_progress"]:
                client.beta.threads.runs.cancel(
                    thread_id=thread_id,
                    run_id=run.id
                )
        return True
    except Exception as e:
        return False

def get_assistant_response(client, thread_id: str):
    """Get the assistant's response"""
    try:
        messages = client.beta.threads.messages.list(thread_id=thread_id)
        return messages.data[0].content[0].text.value
    except Exception as e:
        st.session_state.last_error = str(e)
        st.error(f"Error getting response: {str(e)}")
        return None

def display_chat_history(chat):
    """Display the chat history"""
    if not chat['messages']:
        # Show empty state without welcome message
        pass
    else:
        for message in chat['messages']:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

def render_sidebar():
    """Render the sidebar"""
    with st.sidebar:
        st.title("🤖 AI Chat")
        
        # New chat button
        if st.button("➕ New Chat", use_container_width=True):
            create_new_chat()
            st.rerun()
        
        st.divider()
        
        # Chat history
        if st.session_state.chats:
            st.subheader("Chat History")
            
            # Sort chats by creation time (newest first)
            sorted_chats = sorted(
                st.session_state.chats.values(), 
                key=lambda x: x['created_at'], 
                reverse=True
            )
            
            for chat in sorted_chats:
                is_active = chat['id'] == st.session_state.current_chat_id
                
                # Truncate title if too long
                display_title = chat['title']
                if len(display_title) > 30:
                    display_title = display_title[:27] + "..."
                
                if st.button(
                    display_title,
                    key=f"chat_{chat['id']}",
                    help=f"Created: {chat['created_at'].strftime('%Y-%m-%d %H:%M')}",
                    use_container_width=True
                ):
                    st.session_state.current_chat_id = chat['id']
                    st.rerun()

def stream_response(message_placeholder, response):
    """Stream the response character by character"""
    full_response = ""
    for char in response:
        # Check if user has interrupted
        if not st.session_state.is_responding:
            return full_response
        
        full_response += char
        message_placeholder.markdown(full_response + "▌")
        time.sleep(0.005)  # Much faster speed (0.005 = 200 characters per second)
    
    # Remove the cursor at the end
    message_placeholder.markdown(full_response)
    return full_response

def main():
    # Initialize session state
    initialize_session_state()
    
    # Initialize OpenAI client if not already done
    if st.session_state.client is None:
        st.session_state.client = setup_openai_client(config.OPENAI_API_KEY)
        if st.session_state.client is None:
            st.error("❌ Failed to initialize OpenAI client. Please check your API key.")
            return

    # Login logic
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            with st.form(key='login_form'):
                st.title("Login")
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                submit_button = st.form_submit_button("Login")

                if submit_button:
                    if username == "admin" and password == "1234":
                        st.session_state.logged_in = True
                        st.rerun()
                    else:
                        st.error("Invalid username or password")
        return # Stop execution until logged in

    # Sidebar rendering (moved here to ensure it's only shown after login)
    render_sidebar()

    # Automatically create a new chat if none exists
    if not st.session_state.current_chat_id:
        create_new_chat()
    
    current_chat = get_current_chat()
    # Display chat history (Streamlit-native)
    for message in current_chat['messages']:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    # Always show the chat input bar
    prompt = st.chat_input("Type your message here...")
    if prompt:
        # Check if bot is currently responding
        if st.session_state.is_responding:
            # Stop the current response
            st.session_state.is_responding = False
            if st.session_state.current_message_placeholder:
                st.session_state.current_message_placeholder.markdown("⚠️ Sorry, I couldn't finish that answer.")

        # Add user message to chat
        current_chat['messages'].append({"role": "user", "content": prompt})
        # Update chat title with first message
        if len(current_chat['messages']) == 1:
            new_title = prompt[:30] + "..." if len(prompt) > 30 else prompt
            update_chat_title(current_chat['id'], new_title)
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Send message to assistant
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            st.session_state.current_message_placeholder = message_placeholder
            st.session_state.is_responding = True
            
            thread_id = create_or_get_thread(st.session_state.client, config.ASSISTANT_ID, current_chat)
            if thread_id:
                run_id = send_message(st.session_state.client, thread_id, prompt)
                if run_id:
                    with st.spinner("🤔 Thinking..."):
                        while True:
                            # Check if user has interrupted
                            if not st.session_state.is_responding:
                                break
                                
                            status = get_run_status(st.session_state.client, thread_id, run_id)
                            if status == "completed":
                                response = get_assistant_response(st.session_state.client, thread_id)
                                if response and st.session_state.is_responding:
                                    # Stream the response like ChatGPT
                                    stream_response(message_placeholder, response)
                                    if st.session_state.is_responding:  # Only add if not interrupted
                                        current_chat['messages'].append({"role": "assistant", "content": response})
                                break
                            elif status == "failed":
                                message_placeholder.markdown("Please ask again.")
                                break
                            elif status in ["queued", "in_progress"]:
                                time.sleep(config.POLLING_INTERVAL)
                            else:
                                message_placeholder.markdown("Please ask again.")
                                break
                else:
                    message_placeholder.markdown("Please ask again.")
            else:
                message_placeholder.markdown("Please ask again.")
            
            # Reset response state
            st.session_state.is_responding = False
            st.session_state.current_message_placeholder = None

if __name__ == "__main__":
    main() 