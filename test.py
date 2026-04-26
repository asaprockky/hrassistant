import google.generativeai as genai

genai.configure(api_key="AIzaSyCpkmNlA2hK5i4kOT1mNVNFD7Gdr5fw_bI")

response = genai.GenerativeModel("gemini-2.5-flash").generate_content("Explain how AI works in a few words")


needed_text = 'hello'

def generate_response(needed_text):
    response = genai.GenerativeModel("gemini-2.5-flash").generate_content(needed_text)
    print(response.text)

generate_response('hellooewoewofw')

