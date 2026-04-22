import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")   # explicitly load

class Config:
    MONGO_URI = os.getenv("MONGO_URI")

import cloudinary
import os

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)