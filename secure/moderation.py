from torch.distributions.constraints import boolean
from openai import OpenAI
from config.openAPI import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

def moderation(text: str) -> bool:
    if not isinstance(text, str):
        return "잘못된 입력입니다."
    
    response = client.moderations.create(
        model="omni-moderation-latest",
        input=text
    )

    if response.results[0].flagged:
        return True
    else:
        return False