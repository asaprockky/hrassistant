from email.message import EmailMessage
import ssl
import smtplib
sender = "shokirovabdulfayz@gmail.com"
password = "hqic ybjr ptdz wkgd"
reciever = "sabdulfayiz@gmail.com"



subject  = 'new  video test'

body = """
I published new message
"""

em = EmailMessage()
em["From"] = sender
em["To"] = reciever
em["Subject"] = subject

em.set_content(body)

context = ssl.create_default_context()


with smtplib.SMTP_SSL('smtp.gmail.com', 465, context= context) as smtp:
    smtp.login(sender, password)
    smtp.sendmail(sender, reciever, em.as_string())
    print("success")