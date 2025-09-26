from ..db.collections.files import files_collection
from pdf2image import convert_from_path
from bson import ObjectId
import os
import base64
from openai import OpenAI

client = OpenAI(
    api_key="AIzaSyBqzQ512h-BQiXLlxZaa4_Ej9Lxm3QyfNo",
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


async def process_file(id: str, file_path: str):
    await files_collection.update_one({"_id": ObjectId(id)}, {
        "$set": {
            "status": "processing"
        }
    })
    
    await files_collection.update_one({"_id": ObjectId(id)}, {
        "$set": {
            "status": "Converting to images"
        }
    })
    
    pages = convert_from_path(file_path)
    images = []
    
    for i, page in enumerate(pages):
        image_save_path = f"/mnt/uploads/images/{id}/image-{i}.jpg"
        os.makedirs(os.path.dirname(image_save_path), exist_ok=True)
        page.save(image_save_path, 'JPEG')
        images.append(image_save_path)
        
    await files_collection.update_one({"_id": ObjectId(id)}, {
        "$set": {
            "status": "Converting to images success"
        }
    })
    
    image_base64 = [encode_image(img) for img in images]
    result = client.chat.completions.create(
        model="gemini-2.0-flash",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        # flake8 : noqa
                        "type": "text",
                        "text": "Based on the resume below, Roast this resume.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url":  f"data:image/jpeg;base64,{image_base64[0]}"
                        },
                    },
                ],
            }
        ],
    )
    await files_collection.update_one({"_id": ObjectId(id)}, {
        "$set": {
            "status": "Processed",
            "result": result.choices[0].message.content
        }
    })
    # print(result.choices[0])
    