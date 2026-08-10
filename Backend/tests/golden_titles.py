"""
Golden set: real-world job titles, hand-labeled with the category each should
land in (or None for out of scope). test_categories.py enforces an accuracy
floor over this set, so a regex change that quietly breaks classification
fails the build instead of polluting the next discovery run.

Labels encode *desired* behaviour. Genuinely ambiguous titles (a "UX Engineer"
is design in one company and frontend in another) are left out on purpose —
a golden set full of coin flips enforces nothing.
"""

GOLDEN: list[tuple[str, str | None]] = [
    # --- backend ----------------------------------------------------------
    ("Backend Engineer", "backend"),
    ("Back-End Developer", "backend"),
    ("Back End Software Developer", "backend"),
    ("Senior Backend Engineer (Python)", "backend"),
    ("Node.js Developer", "backend"),
    ("NodeJS Engineer", "backend"),
    ("Python Developer", "backend"),
    ("Java Developer", "backend"),
    ("Golang Engineer", "backend"),
    ("Ruby Developer", "backend"),
    ("PHP Developer", "backend"),
    ("Django Developer", "backend"),
    ("Laravel Developer", "backend"),
    ("Rails Engineer", "backend"),
    ("Spring Developer", "backend"),
    ("FastAPI Developer", "backend"),
    ("Server-Side Engineer", "backend"),
    ("API Engineer", "backend"),
    ("Microservices Engineer", "backend"),
    ("Junior Backend Developer", "backend"),

    # --- frontend ---------------------------------------------------------
    ("Frontend Engineer", "frontend"),
    ("Front-End Developer", "frontend"),
    ("Front End Web Developer", "frontend"),
    ("Senior Frontend Engineer", "frontend"),
    ("React Developer", "frontend"),
    ("React.js Engineer", "frontend"),
    ("Vue Developer", "frontend"),
    ("Angular Engineer", "frontend"),
    ("Next.js Developer", "frontend"),
    ("Svelte Developer", "frontend"),
    ("Web Developer", "frontend"),
    ("Client-Side Engineer", "frontend"),
    ("Junior Front End Developer", "frontend"),

    # --- fullstack --------------------------------------------------------
    ("Full Stack Engineer", "fullstack"),
    ("Full-Stack Developer", "fullstack"),
    ("Fullstack Engineer", "fullstack"),
    ("Senior Full Stack Developer (React/Node)", "fullstack"),
    ("MERN Stack Developer", "fullstack"),
    ("MEAN Stack Developer", "fullstack"),
    ("Full Stack Software Engineer", "fullstack"),
    ("Junior Full Stack Engineer", "fullstack"),

    # --- software_engineer ------------------------------------------------
    ("Software Engineer", "software_engineer"),
    ("Software Developer", "software_engineer"),
    ("Software Development Engineer", "software_engineer"),
    ("Senior Software Engineer", "software_engineer"),
    ("Software Engineer II", "software_engineer"),
    ("SDE", "software_engineer"),
    ("SWE", "software_engineer"),
    ("Product Engineer", "software_engineer"),
    ("Application Developer", "software_engineer"),
    ("Programmer", "software_engineer"),
    ("Engineer I", "software_engineer"),
    ("Junior Developer", "software_engineer"),
    ("Mid-Level Engineer", "software_engineer"),
    ("Developer", "software_engineer"),

    # --- ai_engineer ------------------------------------------------------
    ("AI Engineer", "ai_engineer"),
    ("ML Engineer", "ai_engineer"),
    ("Machine Learning Engineer", "ai_engineer"),
    ("Senior Machine Learning Engineer", "ai_engineer"),
    ("Deep Learning Engineer", "ai_engineer"),
    ("NLP Engineer", "ai_engineer"),
    ("Computer Vision Engineer", "ai_engineer"),
    ("LLM Engineer", "ai_engineer"),
    ("GenAI Engineer", "ai_engineer"),
    ("Generative AI Developer", "ai_engineer"),
    ("MLOps Engineer", "ai_engineer"),
    ("Applied Scientist", "ai_engineer"),
    ("Research Engineer", "ai_engineer"),

    # --- ai_software_engineer ---------------------------------------------
    ("AI Software Engineer", "ai_software_engineer"),
    ("ML Software Engineer", "ai_software_engineer"),
    ("Software Engineer, AI", "ai_software_engineer"),
    ("Software Engineer (Machine Learning)", "ai_software_engineer"),
    ("Software Engineer - GenAI", "ai_software_engineer"),
    ("AI Application Engineer", "ai_software_engineer"),
    ("Machine Learning Software Engineer", "ai_software_engineer"),
    ("AI Product Engineer", "ai_software_engineer"),

    # --- product_design ---------------------------------------------------
    ("Product Designer", "product_design"),
    ("Senior Product Designer", "product_design"),
    ("Digital Product Designer", "product_design"),
    ("Product Design Lead", "product_design"),
    ("Founding Product Designer", "product_design"),
    ("Senior Designer", "product_design"),

    # --- ui_ux ------------------------------------------------------------
    ("UI/UX Designer", "ui_ux"),
    ("UX/UI Designer", "ui_ux"),
    ("UI & UX Designer", "ui_ux"),
    ("Senior UI/UX Designer", "ui_ux"),
    ("UI-UX Designer", "ui_ux"),
    ("UX + UI Designer", "ui_ux"),

    # --- ux_design --------------------------------------------------------
    ("UX Designer", "ux_design"),
    ("Senior UX Designer", "ux_design"),
    ("User Experience Designer", "ux_design"),
    ("Experience Designer", "ux_design"),
    ("Interaction Designer", "ux_design"),
    ("UX Researcher", "ux_design"),
    ("User Researcher", "ux_design"),

    # --- ui_design --------------------------------------------------------
    ("UI Designer", "ui_design"),
    ("Senior UI Designer", "ui_design"),
    ("Visual Designer", "ui_design"),
    ("Interface Designer", "ui_design"),

    # --- out of scope: adjacent tech roles --------------------------------
    ("Data Engineer", None),
    ("Data Analyst", None),
    ("Data Scientist", None),
    ("Senior Data Scientist", None),
    ("Analytics Engineer", None),
    ("DevOps Engineer", None),
    ("Site Reliability Engineer", None),
    ("SRE", None),
    ("Platform Engineer", None),
    ("Infrastructure Engineer", None),
    ("Security Engineer", None),
    ("QA Engineer", None),
    ("Test Engineer", None),
    ("Automation Engineer", None),
    ("Support Engineer", None),
    ("Solutions Architect", None),
    ("Solution Engineer", None),
    ("Sales Engineer", None),

    # --- out of scope: non-engineering ------------------------------------
    ("Product Manager", None),
    ("Senior Product Manager", None),
    ("Project Manager", None),
    ("Technical Writer", None),
    ("Scrum Master", None),
    ("Business Analyst", None),
    ("Graphic Designer", None),
    ("Motion Designer", None),
    ("3D Artist", None),
    ("Illustrator", None),
    ("Marketing Manager", None),
    ("Technical Recruiter", None),
    ("Accountant", None),
    ("Head of Marketing", None),

    # --- out of scope: unrelated ------------------------------------------
    ("Chief of Staff", None),
    ("Customer Success Manager", None),
    ("Operations Associate", None),
    ("Account Executive", None),
    ("Community Manager", None),
    ("Content Strategist", None),
]
