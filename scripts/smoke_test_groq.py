import json
import os
import sys

from dotenv import load_dotenv
from groq import Groq


load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    print("FAILED: GROQ_API_KEY is missing from .env")
    sys.exit(1)


schema = {
    "type": "object",
    "properties": {
        "product_type": {
            "type": "string",
        },
        "maximum_amount": {
            "type": "number",
        },
        "required_features": {
            "type": "array",
            "items": {
                "type": "string",
            },
        },
        "subscription_allowed": {
            "type": "boolean",
        },
        "refundable_required": {
            "type": "boolean",
        },
    },
    "required": [
        "product_type",
        "maximum_amount",
        "required_features",
        "subscription_allowed",
        "refundable_required",
    ],
    "additionalProperties": False,
}


try:
    client = Groq(
        api_key=api_key,
        timeout=20.0,
    )

    response = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract purchasing constraints from the user's "
                    "instruction. Do not invent requirements."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Buy headphones below 3000 rupees. "
                    "They must have active noise cancellation, "
                    "must be refundable, and must not include "
                    "a subscription."
                ),
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "intent_contract",
                "strict": True,
                "schema": schema,
            },
        },
    )

    content = response.choices[0].message.content

    if not content:
        raise ValueError("Groq returned an empty response.")

    result = json.loads(content)

    print("GROQ CONNECTION SUCCESSFUL")
    print(f"Model: {response.model}")
    print(json.dumps(result, indent=2))

except Exception as error:
    print("GROQ CONNECTION FAILED")
    print(f"Error type: {type(error).__name__}")
    print(f"Details: {error}")
    sys.exit(1)