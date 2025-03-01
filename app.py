import os
import openai
from twilio.rest import Client
import logging
from flask import Flask, request, jsonify, session
from dotenv import load_dotenv
from typing import List, Dict
import time
import threading
import re
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# Flask app setup
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "your-secret-key-here")

# Load OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("OPENAI_API_KEY environment variable is missing.")

# Secret phrase for admin access
SECRET_PHRASE = os.getenv("SECRET_PHRASE", "admin access granted")

# Twilio credentials
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
    raise ValueError("Twilio environment variables (ACCOUNT_SID, AUTH_TOKEN, PHONE_NUMBER) are missing.")

# Initialize Twilio client
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Define the AI system prompt
AI_PROMPT = """
You are an AI assistant for ANB Tech Supplies, specializing in iPhone sales. Your role is to assist customers with information about iPhone models, pricing, installment plans, and other inquiries. You also handle customer service and sales requests, providing details on product availability, payment methods, and more. Always respond clearly, politely, and helpfully, staying focused on the customer's question or request. Use short sentences and simple language for easy reading. Maintain context from previous messages to ensure a seamless conversation. Do not include any links unless explicitly instructed. Do not generate or invent banking details; use only the provided details: Account Number: 1773081371, Bank: Capitec, Name: Mr N Nkapele when asked for payment information. When a customer specifies a model, color, and storage (e.g., "Pink iPhone 13, 128GB"), provide details specific to that request.
"""

# Predefined responses (formatted for readability)
PRICE_LIST = """
📌 iPhone Price List – 40% Discount Applied  

Older Models:  
- iPhone X: ~~R7,999~~ Now R4,799  
- iPhone XS: ~~R8,999~~ Now R5,399  
- iPhone XS Max: ~~R9,999~~ Now R5,999  

Mid-Range Models:  
- iPhone 11 Pro: ~~R12,999~~ Now R7,799  
- iPhone 11 Pro Max: ~~R13,999~~ Now R8,399  
- iPhone 12 Pro: ~~R15,999~~ Now R9,599  
- iPhone 12 Pro Max: ~~R16,999~~ Now R10,199  
- iPhone 13: ~~R12,582~~ Now R7,549  

Newer Models:  
- iPhone 13 Pro: ~~R17,999~~ Now R10,799  
- iPhone 13 Pro Max: ~~R18,999~~ Now R11,399  
- iPhone 14 Pro: ~~R20,999~~ Now R12,599  
- iPhone 14 Pro Max: ~~R21,999~~ Now R13,199  

Latest Models:  
- iPhone 15 Pro: ~~R22,999~~ Now R13,799  
- iPhone 15 Pro Max: ~~R23,999~~ Now R14,399  
- iPhone 16 Pro: ~~R24,999~~ Now R14,999  
- iPhone 16 Pro Max: ~~R25,999~~ Now R15,599  
"""

INSTALLMENT_PLAN = """
💳 Monthly Installment Plan  

- Minimum Deposit: R750  
- Flexible Repayment: Up to 24 months  

Example for iPhone X (R4,799):  
- 3 Months: R1,349/month  
- 6 Months: R674/month  
- 12 Months: R337/month  
- 18 Months: R224/month  
- 24 Months: R169/month  

To apply, visit:  
https://applications-yzex.onrender.com/
"""

RECOMMENDATIONS = """
📱 Top Picks for You  

- iPhone 12 Pro + Wireless Charger: R10,899  
- iPhone 14 Pro Max + Case: R14,299  

Want more details or ready to buy?  
Just let me know!
"""

ORDER_FLOW = """
✅ Ready to Buy? Here’s How  

Prices:  
- iPhone 12 Pro: R9,599  
- iPhone 13 Pro Max: R11,399  

Payment Options:  
- 💳 Credit/Debit Card  
- 💳 PayPal  
- 🏦 Bank Transfer:  
  Account Number: 1773081371  
  Bank: Capitec  
  Name: Mr N Nkapele  
- 📅 Installment Plan (up to 24 months)  

For installments, ask me for the link!  
Which option works for you?  

Once paid, reply with "PAID" and your order details!
"""

PICTURE_LINK = """
📸 See iPhones & Customize Your Order  

Visit:  
https://iphone-customizer.onrender.com/
"""

PROMO_MESSAGE = """
🎉 Special Offer!  

Get 5% off your next iPhone this week only.  
Reply "PROMO" to claim it or ask for details!
"""

FOLLOW_UP_MESSAGE = """
👋 Hi there!  

I noticed you haven’t replied yet.  
How can I help you with your iPhone today?
"""

REMINDER_CONFIRMATION = """
⏰ Reminder Set  

I’ll remind you in {time_value} {time_unit}.  
What’s it about?
"""

REMINDER_MESSAGE = """
⏰ Your Reminder  

{reminder_text}  
How can I help you now?
"""

AD_RESPONSE = """
👋 Thanks for replying!  

We’re ANB Tech Supplies.  
We sell the latest iPhones at great prices.  
From the iPhone X to the iPhone 16 Pro Max, we have it all!  
Flexible payment options too.  

See our range and customize your order:  
https://iphone-customizer.onrender.com/  

How can I assist you today?
"""

# Simplified inventory for context (base prices with storage adjustments)
INVENTORY = {
    "iPhone X": {"base_price": 4799, "storage": {64: 0, 128: 500, 256: 1000}, "colors": ["Space Gray", "Silver"]},
    "iPhone XS": {"base_price": 5399, "storage": {64: 0, 256: 600, 512: 1200}, "colors": ["Space Gray", "Silver", "Gold"]},
    "iPhone XS Max": {"base_price": 5999, "storage": {64: 0, 256: 600, 512: 1200}, "colors": ["Space Gray", "Silver", "Gold"]},
    "iPhone 11 Pro": {"base_price": 7799, "storage": {64: 0, 256: 600, 512: 1200}, "colors": ["Space Gray", "Silver", "Gold", "Midnight Green"]},
    "iPhone 11 Pro Max": {"base_price": 8399, "storage": {64: 0, 256: 600, 512: 1200}, "colors": ["Space Gray", "Silver", "Gold", "Midnight Green"]},
    "iPhone 12 Pro": {"base_price": 9599, "storage": {128: 0, 256: 600, 512: 1200}, "colors": ["Graphite", "Silver", "Gold", "Pacific Blue"]},
    "iPhone 12 Pro Max": {"base_price": 10199, "storage": {128: 0, 256: 600, 512: 1200}, "colors": ["Graphite", "Silver", "Gold", "Pacific Blue"]},
    "iPhone 13": {"base_price": 7549, "storage": {128: 0, 256: 500, 512: 1000}, "colors": ["Pink", "Blue", "Midnight", "Starlight", "Red", "Green"]},
    "iPhone 13 Pro": {"base_price": 10799, "storage": {128: 0, 256: 600, 512: 1200}, "colors": ["Graphite", "Gold", "Silver", "Sierra Blue", "Alpine Green"]},
    "iPhone 13 Pro Max": {"base_price": 11399, "storage": {128: 0, 256: 600, 512: 1200}, "colors": ["Graphite", "Gold", "Silver", "Sierra Blue", "Alpine Green"]},
    "iPhone 14 Pro": {"base_price": 12599, "storage": {128: 0, 256: 600, 512: 1200}, "colors": ["Space Black", "Silver", "Gold", "Deep Purple"]},
    "iPhone 14 Pro Max": {"base_price": 13199, "storage": {128: 0, 256: 600, 512: 1200}, "colors": ["Space Black", "Silver", "Gold", "Deep Purple"]},
    "iPhone 15 Pro": {"base_price": 13799, "storage": {128: 0, 256: 600, 512: 1200}, "colors": ["Black Titanium", "White Titanium", "Natural Titanium", "Blue Titanium"]},
    "iPhone 15 Pro Max": {"base_price": 14399, "storage": {256: 0, 512: 600, 1024: 1200}, "colors": ["Black Titanium", "White Titanium", "Natural Titanium", "Blue Titanium"]},
    "iPhone 16 Pro": {"base_price": 14999, "storage": {128: 0, 256: 600, 512: 1200}, "colors": ["Black Titanium", "White Titanium", "Natural Titanium", "Blue Titanium"]},
    "iPhone 16 Pro Max": {"base_price": 15599, "storage": {128: 0, 256: 600, 512: 1200}, "colors": ["Black Titanium", "White Titanium", "Natural Titanium", "Blue Titanium"]}
}

# Sales tracking data
sales_data = {
    "completed": [],  # List of {"phone": str, "item": str, "amount": int, "date": str}
    "pending": [],    # List of {"phone": str, "item": str, "amount": int}
    "promised": []    # List of {"phone": str, "item": str, "amount": int, "day": str}
}

# In-memory store for user states
user_states = {}

# Lock for thread-safe updates
state_lock = threading.Lock()

# Function to query OpenAI GPT-3.5-Turbo
def query_openai(customer_message: str, context: List[Dict[str, str]]) -> str:
    try:
        messages = [{"role": "system", "content": AI_PROMPT}] + context + [{"role": "user", "content": customer_message}]
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7,
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"OpenAI query failed: {e}")
        return "Sorry, I couldn’t process your request right now. How can I assist you otherwise?"

# Check for admin access
def is_admin(message_body: str) -> bool:
    return SECRET_PHRASE.lower() in message_body.lower()

# Generate sales report
def generate_sales_report() -> str:
    today = datetime.now().strftime("%A")
    completed_count = len(sales_data["completed"])
    pending_count = len(sales_data["pending"])
    promised_today = [p for p in sales_data["promised"] if p["day"] == today]
    promised_count = len(promised_today)

    report = "📊 Sales Report\n\n"
    report += f"Completed Sales: {completed_count}\n"
    if completed_count > 0:
        for sale in sales_data["completed"]:
            report += f"- {sale['phone']}: {sale['item']} (R{sale['amount']}) on {sale['date']}\n"
    report += "\n"

    report += f"Pending Sales: {pending_count}\n"
    if pending_count > 0:
        for pend in sales_data["pending"]:
            report += f"- {pend['phone']}: {pend['item']} (R{pend['amount']})\n"
    report += "\n"

    report += f"Promised Today ({today}): {promised_count}\n"
    if promised_count > 0:
        for prom in promised_today:
            report += f"- {prom['phone']}: {prom['item']} (R{prom['amount']})\n"
    
    return report

# Parse specific purchase request
def parse_purchase_request(message: str) -> tuple[str, str, str, int, bool]:
    pattern = r"i(?:'| a)m interested in buying an? (iPhone [^\s(]+(?: Pro Max| Pro)?) \(([^,]+),\s*(\d+GB)\)(?:\s*for\s*R(\d+))?"
    match = re.search(pattern, message.lower())
    if match:
        model = match.group(1)  # e.g., "iphone 13"
        color = match.group(2).strip()  # e.g., "pink"
        storage = match.group(3)  # e.g., "128gb"
        price = int(match.group(4)) if match.group(4) else None  # e.g., 11000 or None
        return model.capitalize(), color.capitalize(), storage, price, True
    return "", "", "", 0, False

# Get price and validate request from INVENTORY
def get_purchase_details(model: str, color: str, storage: str) -> tuple[int, bool]:
    if model in INVENTORY:
        inv = INVENTORY[model]
        storage_int = int(storage.replace("GB", ""))
        if storage_int in inv["storage"] and color in inv["colors"]:
            price = inv["base_price"] + inv["storage"][storage_int]
            return price, True
        return 0, False
    return 0, False

# Send WhatsApp message via Twilio
def send_whatsapp_message(to: str, body: str) -> None:
    try:
        if not to.startswith("+"):
            logging.error(f"Invalid phone number format: {to}")
            return
        max_length = 1600
        chunks = [body[i:i + max_length] for i in range(0, len(body), max_length)]
        for chunk in chunks:
            twilio_client.messages.create(
                body=chunk,
                from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
                to=f"whatsapp:{to}"
            )
        logging.info(f"Message sent to {to}: {body[:50]}...")
    except Exception as e:
        logging.error(f"Failed to send message to {to}: {e}")

# Initialize session context per user
def get_user_context(sender_number: str) -> List[Dict[str, str]]:
    if sender_number not in session:  # Fixed typo: 'sender enjoys_number' to 'sender_number'
        session[sender_number] = []
    return session[sender_number]

# Parse reminder request
def parse_reminder(message: str) -> tuple[int, str, bool]:
    pattern = r"remind me in (\d+) (minute|minutes|hour|hours|day|days)"
    match = re.search(pattern, message.lower())
    if match:
        value, unit = int(match.group(1)), match.group(2)
        if unit.startswith("minute"):
            return value * 60, "minutes", True
        elif unit.startswith("hour"):
            return value * 3600, "hours", True
        elif unit.startswith("day"):
            return value * 24 * 3600, "days", True
    return 0, "", False

# Check if message is an ad reply
def is_ad_reply(message: str) -> bool:
    ad_keywords = ["know more", "tell me more", "about this", "interested", "details", "what’s this", "ad", "advertisement"]
    purchase_keywords = ["buy", "order", "purchase", "pay", "eft", "transfer", "secure"]
    return any(keyword in message.lower() for keyword in ad_keywords) and not any(keyword in message.lower() for keyword in purchase_keywords)

# Follow-up and reminder thread
def follow_up_and_reminder_thread():
    while True:
        with state_lock:
            current_time = time.time()
            for phone_number, state in list(user_states.items()):
                last_message_time = state["last_message_time"]
                follow_up_count = state.get("follow_up_count", 0)
                if follow_up_count < 3 and current_time - last_message_time >= 12 * 3600:
                    logging.info(f"Sending follow-up to {phone_number}, attempt {follow_up_count + 1}")
                    send_whatsapp_message(phone_number, FOLLOW_UP_MESSAGE)
                    state["follow_up_count"] = follow_up_count + 1
                    state["last_message_time"] = current_time
                    user_states[phone_number] = state
                
                reminder_time = state.get("reminder_time", 0)
                reminder_text = state.get("reminder_text", "")
                if reminder_time and current_time >= reminder_time:
                    logging.info(f"Sending reminder to {phone_number}")
                    send_whatsapp_message(phone_number, REMINDER_MESSAGE.format(reminder_text=reminder_text))
                    state["reminder_time"] = 0
                    state["reminder_text"] = ""
                    user_states[phone_number] = state
        time.sleep(60)

# Promo thread
def promo_thread():
    while True:
        with state_lock:
            current_time = time.time()
            for phone_number, state in list(user_states.items()):
                last_promo_time = state.get("last_promo_time", 0)
                if current_time - last_promo_time >= 2 * 24 * 3600:
                    logging.info(f"Sending promo to {phone_number}")
                    send_whatsapp_message(phone_number, PROMO_MESSAGE)
                    state["last_promo_time"] = current_time
                    user_states[phone_number] = state
        time.sleep(3600)

# Start background threads
threading.Thread(target=follow_up_and_reminder_thread, daemon=True).start()
threading.Thread(target=promo_thread, daemon=True).start()

@app.route("/", methods=["GET"])
def home():
    return "Welcome to ANB Tech Supplies AI WhatsApp Assistant!"

@app.route("/webhook", methods=["POST"])
def webhook():
    sender_number = request.form.get("From")
    message_body = request.form.get("Body")

    if not sender_number or not message_body:
        logging.error("Invalid request: Missing 'From' or 'Body'.")
        return jsonify({"status": "error", "message": "Invalid request"}), 400

    sender_number = sender_number.replace("whatsapp:", "")
    logging.info(f"Received message from {sender_number}: {message_body}")

    # Get or initialize user-specific context
    context = get_user_context(sender_number)
    response_message = ""

    # Update user state on reply
    with state_lock:
        if sender_number in user_states:
            user_states[sender_number]["follow_up_count"] = 0
            logging.info(f"Reset follow-up count for {sender_number}")

    # Check for admin access and sales report
    if is_admin(message_body):
        response_message = generate_sales_report()

    # Check for payment confirmation
    elif message_body.lower().startswith("paid"):
        parts = message_body.split(" ", 1)
        if len(parts) > 1:
            order_details = parts[1].strip()
            with state_lock:
                pending = [p for p in sales_data["pending"] if p["phone"] == sender_number]
                if pending:
                    sale = pending[0]
                    sales_data["pending"].remove(sale)
                    sale["date"] = datetime.now().strftime("%Y-%m-%d")
                    sales_data["completed"].append(sale)
                else:
                    sales_data["completed"].append({
                        "phone": sender_number,
                        "item": order_details,
                        "amount": 9599,  # Default price, adjust based on order
                        "date": datetime.now().strftime("%Y-%m-%d")
                    })
            response_message = "✅ Payment received! Thanks for your purchase.\nHow else can I assist you?"
        else:
            response_message = "Please include your order details after 'PAID' (e.g., 'PAID iPhone 12 Pro')."

    # Check for specific purchase request
    elif parse_purchase_request(message_body)[4]:
        model, color, storage, customer_price, is_specific = parse_purchase_request(message_body)
        actual_price, is_valid = get_purchase_details(model, color, storage)
        if is_valid:
            response_message = f"✅ Your {model} ({color}, {storage})\n\n"
            response_message += f"The {color} iPhone 13 is a stunning choice with a sleek design and powerful A15 Bionic chip.\n"
            response_message += f"Price: R{actual_price}\n"
            if customer_price and customer_price != actual_price:
                response_message += f"(You mentioned R{customer_price}, but our price is R{actual_price})\n\n"
            else:
                response_message += "\n"
            response_message += "Payment Options:\n"
            response_message += "- 💳 Credit/Debit Card\n"
            response_message += "- 💳 PayPal\n"
            response_message += "- 🏦 Bank Transfer:\n"
            response_message += "  Account Number: 1773081371\n"
            response_message += "  Bank: Capitec\n"
            response_message += "  Name: Mr N Nkapele\n"
            response_message += "- 📅 Installment Plan (up to 24 months)\n\n"
            response_message += "To proceed, let me know your payment option!\n"
            response_message += "Once paid, reply with 'PAID' and your order details."
            
            with state_lock:
                sales_data["pending"].append({
                    "phone": sender_number,
                    "item": f"{model} ({color}, {storage})",
                    "amount": actual_price
                })
        else:
            response_message = f"Sorry, we don’t have {model} in {color} with {storage} available.\nCheck our full list with 'price' or ask me for alternatives!"

    # Check for reminder request
    elif seconds := parse_reminder(message_body)[0]:
        seconds, unit, is_reminder = parse_reminder(message_body)
        if is_reminder:
            response_message = REMINDER_CONFIRMATION.format(time_value=seconds // (60 if unit == "minutes" else 3600 if unit == "hours" else 24 * 3600), time_unit=unit)

    # Purchase intent check (general)
    elif any(keyword in message_body.lower() for keyword in ["buy", "order", "purchase", "pay", "eft", "transfer", "secure"]):
        response_message = ORDER_FLOW
        with state_lock:
            sales_data["pending"].append({
                "phone": sender_number,
                "item": message_body.lower().split("buy ")[-1] if "buy" in message_body.lower() else "Pending item",
                "amount": 9599
            })

    # Check for ad reply
    elif is_ad_reply(message_body):
        response_message = AD_RESPONSE

    # Other keyword-based responses
    elif any(keyword in message_body.lower() for keyword in ["price", "model", "discount", "cost"]):
        response_message = PRICE_LIST
    elif any(keyword in message_body.lower() for keyword in ["recommend", "suggest", "bundle", "accessories"]):
        response_message = RECOMMENDATIONS
    elif any(keyword in message_body.lower() for keyword in ["installment", "installments", "monthly", "plan"]):
        response_message = INSTALLMENT_PLAN
    elif any(keyword in message_body.lower() for keyword in ["picture", "pictures", "image", "images", "see", "look"]):
        response_message = PICTURE_LINK
    # Fallback to AI
    else:
        response_message = query_openai(message_body, context)

    # Update context
    context.append({"role": "user", "content": message_body})
    context.append({"role": "assistant", "content": response_message})
    if len(context) > 20:
        context = context[-20:]
    session[sender_number] = context

    # Send response
    send_whatsapp_message(sender_number, response_message)

    # Update user state
    with state_lock:
        state = user_states.get(sender_number, {})
        if parse_reminder(message_body)[2] and "about" in message_body.lower():
            seconds, unit, _ = parse_reminder(message_body)
            reminder_text = message_body.split("about", 1)[1].strip()
            state.update({
                "reminder_time": time.time() + seconds,
                "reminder_text": reminder_text
            })
            logging.info(f"Set reminder for {sender_number} in {seconds} seconds: {reminder_text}")
        state.update({
            "last_message_time": time.time(),
            "follow_up_count": 0,
            "last_message": response_message,
            "last_promo_time": state.get("last_promo_time", 0)
        })
        user_states[sender_number] = state
        logging.info(f"Updated state for {sender_number}: {state}")

    return jsonify({"status": "success", "response": response_message})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)