import google.generativeai as genai

genai.configure(api_key="AIzaSyChlmnr711_p1JvLaUdA2-UChyTFB_rpwk")

response = genai.GenerativeModel("gemini-2.5-flash").generate_content("Explain how AI works in a few words")


needed_text = """You are an AI resume evaluator. I will paste a **job description** and a **candidate’s resume text**.  
Your task is to analyze how well the resume matches the job requirements and return the results **strictly in JSON format**.  

### Rules:
- Be concise, factual, and based only on the text provided.
- Do NOT include extra commentary or text outside the JSON.
- If a section is missing, return an empty string or null.
- Always include numerical scores where required.

### JSON format:
{
  "overall_match_score": "<integer between 0 and 100>",
  "advantages": ["<string>", "<string>", "<string>"],
  "disadvantages": ["<string>", "<string>", "<string>"],
  "education": "<summary of education>",
  "experience": "<summary of relevant work experience>",
  "skills_summary": "<brief list or sentence>",
  "skills_match": [
    {
      "skill": "<name of skill>",
      "match_score": "<integer between 0 and 10>",
      "comment": "<brief justification>"
    },
    ...
  ]
}

### Input sections:
JOB DESCRIPTION:
[Paste job description here]

RESUME TEXT:
{[Paste resume text here]}

Now analyze and output only the JSON as specified.

"""

def generate_response():
    response = genai.GenerativeModel("gemini-2.5-flash").generate_content(needed_text)
    print(response.text)
print(response.text)
