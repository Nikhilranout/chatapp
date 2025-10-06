from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout, authenticate, login as auth_login
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import json
import logging

# --- Safe import for groq (won’t crash if missing) ---
try:
    from groq import APIConnectionError
except ImportError:
    APIConnectionError = Exception

logger = logging.getLogger(__name__)

# -------------------- HOME --------------------
def home(request):
    """Renders the homepage with the chatbot form."""
    return render(request, "home.html")


# -------------------- CHAT --------------------
def chat(request):
    """Main chatbot view handling chat sessions and actions."""
    if not request.user.is_authenticated:
        return redirect('login')

    chat_history = request.session.get('chat_history', [])
    error_message = None

    # --- Clear All Messages ---
    if request.method == "POST" and request.POST.get('action') == 'clear_all':
        request.session['chat_history'] = []
        request.session.modified = True
        logger.info(f"{request.user.username} cleared all chat history.")
        return render(request, 'chat.html', {'chat_history': []})

    # --- Delete a Specific Message ---
    if request.method == "POST" and request.POST.get('action') == 'delete_message':
        try:
            index = int(request.POST.get('message_index', -1))
            if 0 <= index < len(chat_history):
                deleted = chat_history.pop(index)
                request.session['chat_history'] = chat_history
                request.session.modified = True
                logger.info(f"{request.user.username} deleted message: {deleted['role']} - {deleted['content'][:60]}")
            else:
                logger.warning(f"Invalid delete index {index} for user {request.user.username}")
        except Exception as e:
            logger.exception(f"Error deleting message for user {request.user.username}: {e}")
        return redirect('chat')

    # --- Send a Message ---
    if request.method == "POST" and request.POST.get('action') == 'send_message':
        content = request.POST.get('content', '').strip()
        if not content or content == 'Enter Your Query...':
            return render(request, 'chat.html', {'chat_history': chat_history})

        # Add user message
        chat_history.append({
            'role': 'user',
            'content': content,
            'timestamp': timezone.now().isoformat()
        })

        try:
            # Configure Gemini API
            genai.configure(api_key=settings.GOOGLE_API_KEY)
            model = genai.GenerativeModel(
                model_name='gemini-2.5-pro',
                generation_config={
                    'temperature': 0.7,
                    'max_output_tokens': 3024,
                },
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                }
            )

            # Build context from chat history
            prev_context = "\n".join([
                f"{'User' if msg['role']=='user' else 'AI'}: {msg['content'][:150]}"
                for msg in chat_history[:-1]
            ])
            full_prompt = f"""
Previous conversation:
{prev_context}

Now respond naturally to this new message:
{content}
"""

            # Generate response
            response = model.generate_content(full_prompt)
            ai_response = getattr(response, 'text', '').strip() or "No response generated."

            # Add AI response
            chat_history.append({
                'role': 'ai',
                'content': ai_response,
                'timestamp': timezone.now().isoformat()
            })
            logger.info(f"Generated AI response for {request.user.username}: {content[:50]}...")

        # --- Specific Gemini Exceptions ---
        except genai.types.StopCandidateException:
            msg = "Response generation stopped by safety filters."
            logger.warning(msg)
            chat_history.append({'role': 'error', 'content': msg, 'timestamp': timezone.now().isoformat()})

        except genai.types.BlockedPromptException:
            msg = "Your prompt was blocked due to safety policies. Please rephrase."
            logger.warning(msg)
            chat_history.append({'role': 'error', 'content': msg, 'timestamp': timezone.now().isoformat()})

        except ValueError as e:
            msg = f"Configuration error: {e}"
            logger.error(msg)
            chat_history.append({'role': 'error', 'content': msg, 'timestamp': timezone.now().isoformat()})

        # --- Network/API or Unexpected Errors ---
        except APIConnectionError as e:
            msg = "Network issue: Failed to connect to AI service. Please try again later."
            logger.error(f"API connection error: {e}")
            chat_history.append({'role': 'error', 'content': msg, 'timestamp': timezone.now().isoformat()})

        except Exception as e:
            msg = f"Unexpected error: {type(e).__name__} - {str(e)}"
            logger.exception(msg)
            chat_history.append({'role': 'error', 'content': msg, 'timestamp': timezone.now().isoformat()})

        # Limit to last 40 messages
        chat_history = chat_history[-40:]
        request.session['chat_history'] = chat_history
        request.session.modified = True

    # --- Final Render ---
    return render(request, 'chat.html', {
        'chat_history': chat_history,
        'error_message': error_message
    })


# -------------------- SIGNUP --------------------
def signup(request):
    """Handles user registration."""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Account created successfully! Please log in.')
            return redirect('login')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserCreationForm()

    return render(request, 'signup.html', {'fm': form})


# -------------------- USER PAGE --------------------
def user(request):
    """Renders the user page."""
    return render(request, 'user.html')


# -------------------- LOGIN --------------------
def login(request):
    """Handles user login."""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user:
            auth_login(request, user)
            return redirect('chat')
        else:
            messages.error(request, "Invalid username or password")

    return render(request, 'login.html')


# -------------------- LOGOUT --------------------
def logoutuser(request):
    """Logs out the current user."""
    logout(request)
    return redirect('login')
