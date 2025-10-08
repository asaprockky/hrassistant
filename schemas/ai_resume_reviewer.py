import google.generativeai as genai

genai.configure(api_key="")

response = genai.GenerativeModel("gemini-2.5-flash").generate_content("Explain how AI works in a few words")
print(response.text)
