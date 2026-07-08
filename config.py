"""
Central configuration for the job-search automation system.
Holds skills, keywords, locations, and runtime settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "jobs.db"

# ──────────────────────────────────────────────
# Secrets (loaded from .env)
# ──────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# ──────────────────────────────────────────────
# My Skills (used for matching)
# ──────────────────────────────────────────────
MY_SKILLS: list[str] = [
    # Programming Languages
    "javascript",
    "typescript",
    "python",
    "java",
    "sql",
    "plpgsql",
    "html",
    "css",
    # Frontend
    "react",
    "react.js",
    "tailwind",
    "tailwind css",
    "vite",
    "framer motion",
    "socket.io",
    "dom",
    "ajax",
    # Backend & Databases
    "node.js",
    "express",
    "express.js",
    "mongodb",
    "mongoose",
    "postgresql",
    "supabase",
    "redis",
    # ML & AI
    "pytorch",
    "huggingface",
    "cnn",
    "resnet",
    "densenet",
    "efficientnet",
    "xgboost",
    "random forest",
    "svm",
    "opencv",
    "machine learning",
    "deep learning",
    # Core CS
    "data structures",
    "algorithms",
    "system design",
    "dbms",
    "operating systems",
    "computer networks",
    "oop",
    # Tools & Architecture
    "git",
    "github",
    "postman",
    "rest api",
    "restful api",
    "websockets",
    "webrtc",
    "jwt",
    "mvc",
    "razorpay",
    "nodemailer",
    "pm2",
    "google colab",
    # General
    "full stack",
    "crm",
    "agile",
]

# ──────────────────────────────────────────────
# Entry-level keywords (boost titles that match)
# ──────────────────────────────────────────────
ENTRY_LEVEL_KEYWORDS: list[str] = [
    "entry level",
    "entry-level",
    "junior",
    "fresher",
    "fresh graduate",
    "graduate",
    "trainee",
    "associate",
    "intern",
    "internship",
    "0-1 year",
    "0-2 year",
    "0 to 1",
    "0 to 2",
    "new grad",
    "campus",
    "early career",
]

# ──────────────────────────────────────────────
# Urgency keywords (flag jobs closing soon)
# ──────────────────────────────────────────────
URGENCY_KEYWORDS: list[str] = [
    "urgent",
    "immediately",
    "immediate joining",
    "asap",
    "closing soon",
    "last date",
    "walk-in",
    "walkin",
    "walk in",
    "spot offer",
    "hiring now",
    "fast-track",
    "priority hiring",
]

# ──────────────────────────────────────────────
# Target locations (Indian cities + remote-india)
# ──────────────────────────────────────────────
TARGET_LOCATIONS: list[str] = [
    "hyderabad",
    "bangalore",
    "bengaluru",
    "mumbai",
    "pune",
    "chennai",
    "delhi",
    "ncr",
    "noida",
    "gurgaon",
    "gurugram",
    "kolkata",
    "ahmedabad",
    "jaipur",
    "kochi",
    "thiruvananthapuram",
    "pan-india",
    "pan india",
    "work from home",
    "wfh",
    "india",
    "telangana",
]

# ──────────────────────────────────────────────
# Blocked locations (reject jobs from these places)
# ──────────────────────────────────────────────
BLOCKED_LOCATIONS: list[str] = [
    "usa", "us-remote", "us remote", "united states",
    "canada", "uk", "london", "europe", "germany", "france",
    "brazil", "singapore", "australia", "japan", "ireland",
    "netherlands", "sweden", "spain", "italy", "poland",
    "new york", "san francisco", "seattle", "austin",
    "boston", "chicago", "los angeles", "denver",
    "toronto", "vancouver", "montreal",
    "remote, us", "remote - us", "remote - usa",
    "remote - canada", "remote - uk", "remote, canada",
    "remote - brazil", "remote - france", "remote - germany",
    "remote - estonia", "remote, emea",
]

# ──────────────────────────────────────────────
# Blocked title keywords (reject senior/lead roles)
# ──────────────────────────────────────────────
BLOCKED_TITLE_KEYWORDS: list[str] = [
    "senior", "staff", "principal", "director",
    "head of", "vp ", "vice president", "chief",
    "architect", "distinguished",
    "10+", "8+", "7+", "6+", "5+",
]

# ──────────────────────────────────────────────
# Scraping settings
# ──────────────────────────────────────────────
REQUEST_TIMEOUT: int = 30          # seconds
REQUEST_DELAY: tuple[float, float] = (1.0, 3.0)  # random delay range between requests
MAX_RETRIES: int = 3
USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# ──────────────────────────────────────────────
# Matching thresholds
# ──────────────────────────────────────────────
MIN_MATCH_SCORE: float = 0.20      # minimum score (0-1) to keep a job
SKILL_WEIGHT: float = 0.50        # weight for skill-match component
LEVEL_WEIGHT: float = 0.30        # weight for entry-level keyword match
LOCATION_WEIGHT: float = 0.20     # weight for location match

# ──────────────────────────────────────────────
# Resume text (for semantic similarity scoring)
# Loaded from SOMESH.txt — the scorer embeds this
# once and compares against each JD.
# ──────────────────────────────────────────────
RESUME_TEXT: str = """
Somesh Chevula — Software Engineer | Full Stack Developer | ML Engineer
B.E. Computer Science and Engineering, Matrusri Engineering College, Hyderabad
CGPA: 8.38 | Expected June 2026
Location: Hyderabad, Telangana, India. Open to relocation and remote.
Email: someshchevula25@gmail.com | Phone: +91-9347679388

EDUCATION:
B.E. Computer Science and Engineering — Matrusri Engineering College, Hyderabad (Oct 2022 – June 2026), CGPA: 8.38
Intermediate (MPC) — TSRJC (BOYS), Sarvail, Telangana (2020 – 2022), Score: 978/1000 (97.8%)

TECHNICAL SKILLS:
Programming Languages: JavaScript (ES6+), TypeScript, Python, Java, SQL, PLpgSQL, HTML5, CSS3.
Frontend: React.js (v19), Tailwind CSS, Vite, Framer Motion, Socket.IO Client, DOM Manipulation, AJAX.
Backend & Databases: Node.js, Express.js (v5), MongoDB (Mongoose), PostgreSQL, Supabase, Redis.
ML & AI: PyTorch, HuggingFace, CNNs (ResNet, DenseNet, EfficientNet), XGBoost, Random Forest, SVM, OpenCV, Grad-CAM.
Core CS: Operating Systems, Computer Networks, DBMS, System Design, Data Structures & Algorithms (DSA).
Tools: Git, GitHub, Postman, Razorpay API, JWT, Nodemailer, RESTful APIs, WebSockets, WebRTC, MVC Architecture, PM2, Google Colab.

EXPERIENCE:
Software Engineer Intern (Frontend & Backend) at Student Tribe (SkyCRM), June 2025 – October 2025.
- Architected a 4-tier CRM application with role-based access (Admins, Managers, Team Leaders, Representatives).
- Developed bulk lead upload, dynamic assignment, and status tracking system.
- Improved dashboard performance using Redis caching for complex visualizations.
- Collaborated in 5-member Agile team designing scalable schemas and frontend interfaces.

PROJECTS:
Qrave/ServeQ — Smart Restaurant Ordering & Queue Management (React 19, Vite, Tailwind CSS, Node.js, Express, Supabase/PostgreSQL, Razorpay, JWT).
- Built unified checkout with UPI (Razorpay Route transfers/GST) and Cash payments.
- Atomic token generation using PostgreSQL RPC and row-level locking (FOR UPDATE).
- Real-time Kitchen Display System and public order tracking via WebSockets.
- Dynamic menu management and admin analytics dashboards with revenue and peak-hour heatmaps.

AlumNet — College Networking Platform (React 19, Node.js, Express, MongoDB, Socket.IO, WebRTC/PeerJS).
- Real-time polymorphic chat and community group messaging with compound database indexing.
- In-browser peer-to-peer audio/video calling using WebRTC and custom socket signaling.
- Full CRUD dashboards for colleges and admins, automated testimonial moderation.

Skin Cancer Diagnostics — ML Major Project (Python, PyTorch, CNN Ensembles, XGBoost, Grad-CAM).
- Multi-feature fusion framework using ISIC 2019/HAM10000 datasets, 8 diagnostic classes.
- 90.18% accuracy, 94.73% Macro AUC using soft-voting ensemble (XGBoost, RF, SVM).
- Safety-first bias minimizing false negatives for malignant classes, Grad-CAM for XAI.

AudioClone — Neural Voice Cloning Pipeline (Python, PyTorch, Whisper, Demucs, Coqui XTTS v2, Google Colab).
- Data pipeline: MP3 to LJSpeech-style dataset using Demucs + Silero VAD.
- Fine-tuned Coqui XTTS v2 GPT-backbone with dynamic hyperparameter tuning.
- Interactive ipywidgets UI for real-time TTS generation.

ACHIEVEMENTS:
450+ DSA problems on LeetCode (Java). Hackathon participant.
"""

# ──────────────────────────────────────────────
# Search keywords (used by portal scrapers)
# ──────────────────────────────────────────────
SEARCH_KEYWORDS: list[list[str]] = [
    ["React", "developer", "fresher"],
    ["Node.js", "developer", "fresher"],
    ["Python", "developer", "fresher"],
    ["Full", "Stack", "Developer", "fresher"],
    ["SDE", "fresher"],
    ["Software", "Engineer", "fresher"],
    ["MERN", "stack", "developer"],
    ["Frontend", "developer", "React", "entry", "level"],
    ["Backend", "developer", "Node.js", "entry", "level"],
    ["Machine", "Learning", "Engineer", "fresher"],
]
