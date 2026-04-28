from flask import Flask
from flask_pymongo import PyMongo
from flask_cors import CORS
from config import Config
from flask import request, jsonify
import bcrypt
from datetime import datetime
import jwt
import os
from functools import wraps
import cloudinary.uploader

app = Flask(__name__)
app.config.from_object(Config)

CORS(
    app,
    supports_credentials=True,
    resources={
        r"/*": {
            "origins": [
                r"https://.*\.lovable\.app",
                "http://localhost:5173",
                "http://localhost:8080",
                "https://trackademic-fd.vercel.app"
            ]
        }
    }
)
# CORS(app)
mongo=PyMongo(app)

# from dotenv import load_dotenv            // add these line only when running locally
# load_dotenv(dotenv_path=".env")   # explicitly load

import os
import cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

@app.route('/')
def home():
    return "Welcome to the Student Activities API!"

@app.route("/test-db")
def test_db():
    mongo.db.test.insert_one({"message": "Hello, MongoDB!"})
    return "Database connection successful and test document inserted!"
SECRET_KEY = os.getenv("SECRET_KEY")
@app.route("/register", methods=["POST"])
def register():
    data = request.json

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    role = data.get("role")
    usn = data.get("usn")

    # Validation
    if not name or not email or not password or not role:
        return jsonify({"error": "Missing fields"}), 400

    if role == "student" and not usn:
        return jsonify({"error": "USN is required for students"}), 400
    
    FACULTY_SECRET_CODE = os.getenv("FACULTY_SECRET_CODE")
    if role == "faculty":
        faculty_code = data.get("faculty_code")
        if faculty_code != FACULTY_SECRET_CODE:
            return jsonify({"error": "Invalid faculty access code"}), 403

    # Check existing user
    if mongo.db.users.find_one({"email": email}):
        return jsonify({"error": "User already exists"}), 400

    # Hash password
    hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    user = {
        "name": name,
        "email": email,
        "password": hashed_pw,
        "role": role,
        "usn": usn if role == "student" else None,
        "created_at": datetime.utcnow()
    }

    mongo.db.users.insert_one(user)

    token = jwt.encode(
        {"email": email, "role": role},
        os.getenv("SECRET_KEY"),
        algorithm="HS256"
    )

    return jsonify({
        "token": token,
        "user": {
            "name": name,
            "email": email,
            "role": role,
            "usn": usn
        }
    }), 201


    # return jsonify({"msg": "User registered successfully"}), 201


@app.route("/login", methods=["POST"])
def login():
    data = request.json

    email = data.get("email")
    password = data.get("password")

    user = mongo.db.users.find_one({"email": email})

    if not user:
        return jsonify({"error": "User not found"}), 404

    if not bcrypt.checkpw(password.encode('utf-8'), user["password"]):
        return jsonify({"error": "Invalid password"}), 401

    token = jwt.encode({
        "user_id": str(user["_id"]),
        "role": user["role"]
    }, os.getenv("SECRET_KEY"), algorithm="HS256")

    return jsonify({
        "token": token,
        "role": user["role"]
    })

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization")

        if not token:
            return jsonify({"error": "Token missing"}), 401

        try:
            token = token.split(" ")[1]  # Remove "Bearer "
            data = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=["HS256"])
        except:
            return jsonify({"error": "Invalid token"}), 401

        return f(data, *args, **kwargs)

    return decorated

from datetime import datetime

@app.route("/create-profile", methods=["POST"])
@token_required
def create_profile(current_user):
    if current_user["role"] != "student":
        return jsonify({"error": "Only students can create profile"}), 403

    data = request.json

    # Check if profile already exists
    if mongo.db.profiles.find_one({"user_id": current_user["user_id"]}):
        return jsonify({"error": "Profile already exists"}), 400

    profile = {
        "user_id": current_user["user_id"],
        "department": data.get("department"),
        "semester": data.get("semester"),
        "profile_image": "https://cloudinary-url",
        "headline": data.get("headline", ""), 
        "bio": data.get("bio", ""),
        "skills": [],
        "score": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()

    }

    mongo.db.profiles.insert_one(profile)

    return jsonify({"msg": "Profile created successfully"})

@app.route("/get-profile", methods=["GET"])
@token_required
def get_profile(current_user):
    profile = mongo.db.profiles.find_one({
        "user_id": current_user["user_id"]
    })

    if not profile:
        return jsonify({"error": "Profile not found"}), 404

    profile["_id"] = str(profile["_id"])

    return jsonify(profile)

def calculate_score(user_id):
    skills_count = len(list(mongo.db.profiles.find_one(
        {"user_id": user_id}
    ).get("skills", [])))

    projects_count = mongo.db.projects.count_documents({"user_id": user_id})
    cert_count = mongo.db.certifications.count_documents({"user_id": user_id})
    hack_count = mongo.db.hackathons.count_documents({"user_id": user_id})
    intern_count = mongo.db.internships.count_documents({"user_id": user_id})

    score = (
        skills_count * 2 +
        projects_count * 5 +
        cert_count * 3 +
        hack_count * 4 +
        intern_count * 6
    )

    return score

def update_score(user_id):
    score = calculate_score(user_id)

    mongo.db.profiles.update_one(
        {"user_id": user_id},
        {"$set": {"score": score}}
    )

@app.route("/add-project", methods=["POST"])
@token_required
def add_project(current_user):
    if current_user["role"] != "student":
        return jsonify({"error": "Only students allowed"}), 403

    data = request.json

    project = {
        "user_id": current_user["user_id"],
        "title": data.get("title"),
        "description": data.get("description"),
        "tech_stack": data.get("tech_stack", []),
        "github_link": data.get("github_link"),
        "isPublic": data.get("isPublic", True)
    }

    mongo.db.projects.insert_one(project)

    update_score(current_user["user_id"])

    return jsonify({"msg": "Project added"})


@app.route("/add-certification", methods=["POST"])
@token_required
def add_certification(current_user):
    if current_user["role"] != "student":
        return jsonify({"error": "Only students allowed"}), 403

    data = request.json

    cert = {
        "user_id": current_user["user_id"],
        "title": data.get("title"),
        "issuer": data.get("issuer"),
        "certificate_link": data.get("certificate_link"),  # Cloudinary URL
        "isPublic": data.get("isPublic", True)
    }

    mongo.db.certifications.insert_one(cert)

    update_score(current_user["user_id"])

    return jsonify({"msg": "Certification added"})


@app.route("/add-hackathon", methods=["POST"])
@token_required
def add_hackathon(current_user):
    if current_user["role"] != "student":
        return jsonify({"error": "Only students allowed"}), 403

    data = request.json

    hack = {
        "user_id": current_user["user_id"],
        "name": data.get("name"),
        "position": data.get("position"),
        "isPublic": data.get("isPublic", True)
    }

    mongo.db.hackathons.insert_one(hack)

    update_score(current_user["user_id"])

    return jsonify({"msg": "Hackathon added"})


@app.route("/add-internship", methods=["POST"])
@token_required
def add_internship(current_user):
    if current_user["role"] != "student":
        return jsonify({"error": "Only students allowed"}), 403

    data = request.json

    intern = {
        "user_id": current_user["user_id"],
        "company": data.get("company"),
        "role": data.get("role"),
        "duration": data.get("duration"),
        "isPublic": data.get("isPublic", True)
    }

    mongo.db.internships.insert_one(intern)

    update_score(current_user["user_id"])

    return jsonify({"msg": "Internship added"})


@app.route("/upload", methods=["POST"])
@token_required
def upload_file(current_user):
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]

    try:
        result = cloudinary.uploader.upload(file)
        return jsonify({
            "url": result["secure_url"]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

from bson import ObjectId
@app.route("/top-students-all", methods=["GET"])
def top_students_all():
    result = {}

    branches = mongo.db.profiles.distinct("department")

    for branch in branches:
        students = list(mongo.db.profiles.find(
            {"department": branch}
        ).sort("score", -1).limit(5))

        enriched = []

        for s in students:
            user = mongo.db.users.find_one({
                "_id": ObjectId(s["user_id"])
            })

            if not user:
                continue  # skip broken data

            enriched.append({
                "name": user["name"],
                "usn": user.get("usn"),
                "department": s["department"],
                "semester": s["semester"],
                "score": s["score"]
            })

        result[branch] = enriched

    return jsonify(result)

#AI integration part
# from sentence_transformers import SentenceTransformer
# import numpy as np

# model = SentenceTransformer('all-mpnet-base-v2') # more accurate but heavier, can switch to smaller one for faster performance , can deploy this on render
# model = SentenceTransformer('all-MiniLM-L6-v2')  # smaller and faster

# REMOVE this from the top level:
# model = SentenceTransformer('all-MiniLM-L6-v2')  ❌

# ADD this instead:
# _sentence_model = None

# def get_sentence_model():
#     global _sentence_model
#     if _sentence_model is None:
#         _sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
#     return _sentence_model

# from fastembed import TextEmbedding
# model = TextEmbedding("BAAI/bge-small-en-v1.5")



def build_student_text(profile):
    skills = ", ".join([s["name"] for s in profile.get("skills", [])])

    projects = list(mongo.db.projects.find({"user_id": profile["user_id"]}))
    project_text = " ".join([
        f"Worked on project {p.get('title','')} using {', '.join(p.get('tech_stack', []))}. {p.get('description','')}"
        for p in projects
    ])

    internships = list(mongo.db.internships.find({"user_id": profile["user_id"]}))
    intern_text = " ".join([
        f"Completed internship as {i.get('role','')} at {i.get('company','')}"
        for i in internships
    ])

    certifications = list(mongo.db.certifications.find({"user_id": profile["user_id"]}))
    cert_text = " ".join([
        f"Certified in {c.get('title','')} from {c.get('issuer','')}"
        for c in certifications
    ])

    text = f"""
    This student has skills in {skills}.
    {project_text}
    {intern_text}
    {cert_text}
    """

    return text

def update_embedding(user_id):
    pass  # not needed in deployment

@app.route("/semantic-search", methods=["GET"])
def semantic_search():
    query = request.args.get("q")
    
    profiles = list(mongo.db.profiles.find({
        "$or": [
            {"skills.name": {"$regex": query, "$options": "i"}},
            {"headline": {"$regex": query, "$options": "i"}},
            {"bio": {"$regex": query, "$options": "i"}}
        ]
    }))

    if not profiles:
        return jsonify([])

    results = []
    for profile in profiles:
        user = mongo.db.users.find_one({"_id": ObjectId(profile["user_id"])})
        if not user:
            continue
        results.append({
            "name": user["name"],
            "usn": user.get("usn"),
            "score": profile.get("score")
        })

    return jsonify(results[:5])



@app.route("/add-skill", methods=["POST"])
@token_required
def add_skill(current_user):
    data = request.json

    mongo.db.profiles.update_one(
        {"user_id": current_user["user_id"]},
        {"$push": {
            "skills": {
                "name": data.get("skill"),
                "isPublic": True
            }
        }}
    )

    update_score(current_user["user_id"])
    update_embedding(current_user["user_id"])

    return jsonify({"msg": "Skill added"})

import google.generativeai as genai
import os

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model_gemini = genai.GenerativeModel("gemini-2.5-flash")

# for model in genai.list_models():
#     print(model.name, "->", model.supported_generation_methods)

def ask_gemini(prompt):
    try:
        response = model_gemini.generate_content(prompt)
        return response.text
    except Exception as e:
        print("Gemini Error:", e)  
        return f"Error from Gemini {str(e)}"
    
import re

def extract_semester(query):
    match = re.search(r'\b(\d+)\b', query)
    if match:
        return int(match.group(1))
    return None

@app.route("/chat", methods=["POST"])
@token_required
def chat(current_user):
    data = request.json
    query = data.get("message")
    query_lower = query.lower()

    # =========================
    # 🔥 INTENT: TOP STUDENTS
    # =========================
    if "top" in query_lower or "best" in query_lower:
        students = list(mongo.db.profiles.find().sort("score", -1).limit(3))

        response = "🏆 Top students are:\n"
        for s in students:
            user = mongo.db.users.find_one({
                "_id": ObjectId(s["user_id"])
            })
            response += f"- {user['name']} (Score: {s['score']})\n"

        return jsonify({"reply": response})
        
    # =========================
    # 🔥 INTENT: SEMESTER FILTER
    # =========================

    sem = extract_semester(query_lower)

    if "sem" in query_lower or "semester" in query_lower:
        students = list(mongo.db.profiles.find({
            "semester": sem
        }))

        if not students:
            return jsonify({
                "reply": f"No students found in semester {sem}."
            })

        response = f"Students in semester {sem}:\n"

        for s in students:
            user = mongo.db.users.find_one({
                "_id": ObjectId(s["user_id"])
            })

            response += f"- {user['name']} (Score: {s['score']})\n"

        return jsonify({"reply": response})

    # =========================
    # 🔥 INTENT: DB SEARCH (regex)
    # =========================
    if any(word in query_lower for word in ["student", "skills", "project", "internship"]):

        profiles = list(mongo.db.profiles.find({
            "$or": [
                {"skills.name": {"$regex": query, "$options": "i"}},
                {"headline": {"$regex": query, "$options": "i"}},
                {"bio": {"$regex": query, "$options": "i"}}
            ]
        }))

        if not profiles:
            return jsonify({"reply": "No matching students found."})

        response = "🤖 Relevant students:\n"
        for p in profiles[:3]:
            user = mongo.db.users.find_one({"_id": ObjectId(p["user_id"])})
            if not user:
                continue
            response += f"- {user['name']} (Score: {p.get('score')})\n"

        return jsonify({"reply": response})

    # =========================
    # 🔥 FALLBACK: GEMINI
    # =========================

    context = build_context()

    prompt = f"""
    You are an assistant for a student management system.

    Context:
    {context}

    Question:
    {query}

    Answer clearly and concisely.
    """

    gemini_reply = ask_gemini(prompt)

    return jsonify({"reply": gemini_reply})

def build_context():
    profiles = list(mongo.db.profiles.find().limit(5))

    context = "Student Data:\n"

    for p in profiles:
        user = mongo.db.users.find_one({"_id": ObjectId(p["user_id"])})
        skills = ", ".join([s["name"] for s in p.get("skills", [])])

        context += f"{user['name']} has skills in {skills} and score {p.get('score')}.\n"

    return context

@app.route("/upload-profile-image", methods=["POST"])
@token_required
def upload_profile_image(current_user):
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]

    try:
        result = cloudinary.uploader.upload(
            file,
            folder="profile_images"
        )

        image_url = result["secure_url"]

        # Save in profile
        mongo.db.profiles.update_one(
            {"user_id": current_user["user_id"]},
            {"$set": {"profile_image": image_url}}
        )

        return jsonify({
            "msg": "Profile image uploaded",
            "url": image_url
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/update-profile", methods=["POST"])
@token_required
def update_profile(current_user):
    data = request.json

    mongo.db.profiles.update_one(
        {"user_id": current_user["user_id"]},
        {"$set": {
            "bio": data.get("bio"),
            "headline": data.get("headline")
        }}
    )

    return jsonify({"msg": "Profile updated"})

@app.route("/get-full-profile", methods=["GET"])
@token_required
def get_full_profile(current_user):

    profile = mongo.db.profiles.find_one({
        "user_id": current_user["user_id"]
    })

    user = mongo.db.users.find_one({
        "_id": ObjectId(current_user["user_id"])
    })

    projects = list(mongo.db.projects.find({
        "user_id": current_user["user_id"]
    }))

    internships = list(mongo.db.internships.find({
        "user_id": current_user["user_id"]
    }))

    certifications = list(mongo.db.certifications.find({
        "user_id": current_user["user_id"]
    }))

    return jsonify({
        "name": user["name"],
        "email": user["email"],
        "usn": user.get("usn"),
        "profile_image": profile.get("profile_image"),
        "headline": profile.get("headline"),
        "bio": profile.get("bio"),
        "skills": profile.get("skills"),
        "projects": projects,
        "internships": internships,
        "certifications": certifications
    })

if __name__ == '__main__':
    app.run(debug=True)

# okay will move to frontend part now 
# covering all the features and displaying with robust UI/UX(complete dark themed by default) and with integrated  AI features in the frontend as well for better user experience give me tagda lovalble prompt