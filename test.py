import pandas as pd
import uuid
import json
import random

# Configuration
categories = ['SQL', 'Python', 'Data Science', 'SSRS']
difficulty_levels = [1, 2, 3]
points_options = [1.0, 5.0, 10.0]

def generate_options():
    opts = []
    for i in range(4):
        opts.append({
            "id": str(uuid.uuid4()),
            "text": f"Option {chr(65+i)}"
        })
    return opts

# Generate 100 rows
data = []
for i in range(100):
    cat = random.choice(categories)
    options_list = generate_options()
    correct_uuid = random.choice(options_list)['id']
    
    data.append({
        "id": str(uuid.uuid4()),
        "text": f"Question {i+1}: What is a key concept in {cat}?",
        "correct_answer": correct_uuid,
        "options": json.dumps(options_list),
        "difficulty_level": random.choice(difficulty_levels),
        "category": cat,
        "points": random.choice(points_options)
    })

# Save to CSV
df = pd.DataFrame(data)
df.to_csv("100_questions_import.csv", index=False)
print("File '100_questions_import.csv' has been created successfully!")