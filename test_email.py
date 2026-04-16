import smtplib
from email.message import EmailMessage

# --- EDIT THESE TWO LINES ---
EMAIL_ADDRESS = "kunvariya.dk@gmail.com"
APP_PASSWORD = "cwpctdztwwohcjhe"
# ----------------------------

msg = EmailMessage()
msg.set_content("This is a test email to verify Google SMTP is working.")
msg['Subject'] = "SMTP Test"
msg['From'] = EMAIL_ADDRESS
msg['To'] = EMAIL_ADDRESS  # Sending it to yourself

print("Attempting to connect to Gmail...")

try:
    # Connect to Google's SMTP server on port 587
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.set_debuglevel(1)  # This will print EXACTLY what goes wrong

    server.ehlo()
    print("Starting TLS encryption...")
    server.starttls()
    server.ehlo()

    print("Attempting to log in...")
    # This is the line that will fail if the App Password isn't working
    server.login(EMAIL_ADDRESS, APP_PASSWORD)

    print("Login successful! Sending email...")
    server.send_message(msg)
    print("✅ Email sent successfully!")

    server.quit()

except Exception as e:
    print(f"\n❌ FAILED: {e}")