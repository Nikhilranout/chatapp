from django.shortcuts import render,redirect
import json
import google.generativeai as genai
from django.conf import settings 
import logging
from groq import APIConnectionError
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import logout,authenticate,login as  auth_login
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from django.utils import timezone 

def home(request):
    """Renders the homepage with the chatbot form."""
    return render(request, "home.html")




logger = logging.getLogger(__name__)


def chat(request):
    if not request.user.is_authenticated:
        return redirect('login')
    # Initialize session history if not present (list of dicts with 'role', 'content', 'timestamp')
    if 'chat_history' not in request.session:
        request.session['chat_history'] = []
    chat_history = request.session['chat_history']

    # Handle clear all history (POST for security)
    if request.method == "POST" and request.POST.get('action') == 'clear_all':
        request.session['chat_history'] = []
        request.session.modified = True
        logger.info(f"User  {request.user.username} cleared all chat history.")
        return render(request, 'chat.html', {'chat_history': []})

    # Handle delete individual message (POST with index)
    if request.method == "POST" and request.POST.get('action') == 'delete_message':
        try:
            index = int(request.POST.get('message_index', -1))
            if 0 <= index < len(chat_history):
                deleted_msg = chat_history.pop(index)
                request.session['chat_history'] = chat_history
                request.session.modified = True
                logger.info(f"User  {request.user.username} deleted message at index {index}: {deleted_msg['role']}")
            else:
                logger.warning(f"Invalid delete index {index} for user {request.user.username}")
        except (ValueError, IndexError) as e:
            logger.error(f"Delete message error: {e}")
        # Redirect to self to refresh (avoids form resubmission)
        return redirect('chat')  # Assuming your URL name is 'chat'

    error_message = None

    if request.method == "POST" and request.POST.get('action') == 'send_message':
        content = request.POST.get('content', '').strip()
        if not content or content == 'Enter Your Query...':
            return render(request, 'chat.html', {'chat_history': chat_history})

        # Add user message to history with timestamp
        user_msg = {
            'role': 'user', 
            'content': content,
            'timestamp': timezone.now().isoformat()  # ISO for easy JS parsing
        }
        chat_history.append(user_msg)
        
        ai_response = None
        try:
            genai.configure(api_key=settings.GOOGLE_API_KEY)
            
            # Check library version for compatibility warnings
            version = getattr(genai, '__version__', 'unknown')
            logger.info(f"Using google-generativeai version: {version}")
            
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

            # Build context from current history (excludes the just-added user message for prompt)
            prev_context_parts = []
            for msg in chat_history[:-1]:
                role_prefix = ":User  " if msg['role'] == 'user' else "AI: "
                truncated_msg = msg['content'][:150] + "..." if len(msg['content']) > 150 else msg['content']
                prev_context_parts.append(role_prefix + truncated_msg)
            
            prev_context = "\n".join(prev_context_parts) if prev_context_parts else ""
            full_prompt = f"""Previous conversation context:
{prev_context}

Now respond to the current user query: {content}

Please respond naturally, continuing the conversation if context is provided."""
            
            response = model.generate_content(full_prompt)
            ai_response = response.text.strip() if hasattr(response, 'text') and response.text else "No response generated from the model."
            
            # Add AI response to history with timestamp
            ai_msg = {
                'role': 'ai', 
                'content': ai_response,
                'timestamp': timezone.now().isoformat()
            }
            chat_history.append(ai_msg)
            
            logger.info(f"Generated response for query: {content[:50]}...")

        except genai.types.StopCandidateException:
            error_msg = "Response generation was stopped due to safety filters."
            chat_history.append({'role': 'error', 'content': error_msg, 'timestamp': timezone.now().isoformat()})
        except genai.types.BlockedPromptException:
            error_msg = "Your prompt was blocked due to safety policies. Please rephrase."
            chat_history.append({'role': 'error', 'content': error_msg, 'timestamp': timezone.now().isoformat()})
        except ValueError as e:
            error_msg = f"Configuration error: {str(e)}"
            logger.error(f"ValueError in chat view: {str(e)}")
            chat_history.append({'role': 'error', 'content': error_msg, 'timestamp': timezone.now().isoformat()})
        except Exception as e:
            error_msg = f"An unexpected error occurred: {str(e)}. Please check your setup."
            logger.error(f"Unexpected error in chat view: {str(e)}")
            chat_history.append({'role': 'error', 'content': error_msg, 'timestamp': timezone.now().isoformat()})

        # Limit history to last 40 messages
        if len(chat_history) > 40:
            chat_history = chat_history[-40:]
        request.session['chat_history'] = chat_history
        request.session.modified = True

    # Pass to template
    context = {
        'chat_history': chat_history,
        'error_message': error_message
    }
    return render(request, 'chat.html', context)








def signup(request):
    if request.method == 'POST':
        frm = UserCreationForm(request.POST)  
        if frm.is_valid():
            user = frm.save() 
            messages.success(request, 'Account created successfully! Please log in.')
            return redirect('login') 
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        frm = UserCreationForm()  

    return render(request, 'signup.html', {'fm': frm})

def user(request):
    return render(request,'user.html')

def login(request):
 

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

def logoutuser(request):
    logout(request)
    return redirect('login')
