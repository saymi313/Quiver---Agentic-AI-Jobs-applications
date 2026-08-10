"""
Cold-email templates for the prospecting pipeline.

Each template is shared by:
    - build_excel.py          (renders the 'Cold Email Templates' sheet)
    - send_applications.py    (actually sends the email via Gmail SMTP)

Placeholders supported (any missing ones are left unchanged):
    {Company}                 -> company name
    {Vertical}                -> vertical bucket
    {HiringManager}           -> defaults to 'Hiring Team'
    {ContactName}             -> defaults to 'there'
    {OneLineAboutCompany}     -> the 'notes' field from companies_data.py
    {CustomRequirement}       -> the 'custom' field from companies_data.py
"""

CANDIDATE_NAME = "Usairam Saeed"
CANDIDATE_EMAIL = "saeed.usairam@gmail.com"
CANDIDATE_PHONE = "+92-301-8165385"


EMAIL_TEMPLATES = [
    {
        "id": "T1",
        "name": "Generic - Full Stack (Default)",
        "use_for": "Any vertical when no specialised template fits",
        "subject": "Full Stack Engineer (React / Node.js) interested in {Company}",
        "body": (
            "Hi {HiringManager},\n\n"
            "I'm Usairam Saeed, a Full Stack Product Engineer (React, Node.js, MongoDB) "
            "currently building SaaS products used by 500 - 2,000+ users. I came across "
            "{Company} while researching {Vertical} teams in Pakistan and I'm drawn to "
            "{OneLineAboutCompany}.\n\n"
            "Recent highlights from my work:\n"
            "- Shipped Scholarslee, a mentorship SaaS with Stripe payments and Socket.io real-time chat - "
            "cut booking time by 70% and achieved a 4.9/5 mentor rating.\n"
            "- Built the Sweden Relocators portal for 2,000+ users; improved UX by 35% and cut load time "
            "to under 1.8s.\n"
            "- Created Neuro Mark, an AI-driven HR SaaS with 98.7% accurate facial-recognition attendance "
            "used by 15+ corporate clients.\n\n"
            "For {Company} specifically I think I'd be useful for: {CustomRequirement}.\n\n"
            "If the team is hiring for full-stack or product engineering, I'd love 15 minutes to share how "
            "my experience could help. Resume attached.\n\n"
            "Best regards,\n"
            "Usairam Saeed\n"
            "saeed.usairam@gmail.com | +92-301-8165385\n"
            "LinkedIn | GitHub | Portfolio"
        ),
    },
    {
        "id": "T2",
        "name": "AI / Data Science (Europass CV)",
        "use_for": "AI & Data Science",
        "subject": "AI + Full Stack Engineer - interested in {Company}",
        "body": (
            "Hi {HiringManager},\n\n"
            "I'm Usairam Saeed - a Full Stack Engineer with a production AI/ML focus. Over the last year "
            "I built Neuro Mark, an AI-driven HR SaaS using deep-learning facial recognition (98.7% accuracy), "
            "now serving 15+ corporate clients and processing 10,000+ daily attendance records with zero downtime. "
            "Your work at {Company} on {OneLineAboutCompany} is exactly the kind of problem space I want to contribute to.\n\n"
            "Stack: React, Node.js, Express, MongoDB, Python, ML/NLP, Docker/Kubernetes.\n"
            "Certifications: Stanford Complete Machine Learning, IBM Agile & Scrum.\n\n"
            "Where I'd plug in at {Company}: {CustomRequirement}.\n\n"
            "Europass CV attached. Would you have 15 minutes to explore a fit?\n\n"
            "Best regards,\n"
            "Usairam Saeed\n"
            "saeed.usairam@gmail.com | +92-301-8165385\n"
            "LinkedIn | GitHub | Portfolio"
        ),
    },
    {
        "id": "T3",
        "name": "FinTech / Payments",
        "use_for": "Finance/FinTech",
        "subject": "Full Stack Engineer with payments + real-time experience - {Company}",
        "body": (
            "Hi {HiringManager},\n\n"
            "I've been following {Company}'s work on {OneLineAboutCompany} and wanted to reach out.\n\n"
            "I'm a Full Stack Engineer (React, Node.js, MongoDB) with direct experience building "
            "payment flows and real-time systems:\n"
            "- Integrated Stripe in Scholarslee with a 100% payment success rate across 500+ monthly users.\n"
            "- Designed real-time chat (Socket.io) and a calendar scheduler that reduced booking time by 70%.\n"
            "- Shipped production systems for 2,000+ users with sub-1.8s page loads.\n\n"
            "What I'd bring to {Company}: {CustomRequirement}.\n\n"
            "Resume attached. Happy to jump on a 15-minute call.\n\n"
            "Best regards,\n"
            "Usairam Saeed\n"
            "saeed.usairam@gmail.com | +92-301-8165385"
        ),
    },
    {
        "id": "T4",
        "name": "HealthTech / EdTech (SaaS focus)",
        "use_for": "Healthcare/HealthTech, Education & Training",
        "subject": "Full Stack Engineer - scheduling, real-time, UX at scale",
        "body": (
            "Hi {HiringManager},\n\n"
            "I'm reaching out because {Company}'s mission around {OneLineAboutCompany} aligns with the "
            "kind of impact I want to build. As a Full Stack Engineer (React, Node.js, MongoDB), my "
            "recent production work has centred exactly on the problems your platform likely faces:\n\n"
            "- Booking & scheduling: built a calendar-integrated mentor booking flow (Scholarslee, "
            "500+ monthly users, 4.9/5 rating).\n"
            "- Real-time communication: Socket.io chat + notifications in production.\n"
            "- UX depth: improved measured usability by 35% and brought page loads under 1.8s on the "
            "Sweden Relocators portal (2,000+ users).\n\n"
            "Relevant to {Company}: {CustomRequirement}.\n\n"
            "Resume attached. Open to a 15-minute call at your convenience.\n\n"
            "Best regards,\n"
            "Usairam Saeed\n"
            "saeed.usairam@gmail.com | +92-301-8165385\n"
            "LinkedIn | GitHub | Portfolio"
        ),
    },
    {
        "id": "T5",
        "name": "E-Commerce / Marketplace",
        "use_for": "E-Commerce & Retail, Food & Agriculture, Travel & Hospitality, Aviation & Logistics",
        "subject": "Full Stack Engineer interested in scaling {Company}'s product",
        "body": (
            "Hi {HiringManager},\n\n"
            "I'm Usairam Saeed, a Full Stack Product Engineer who's shipped marketplace-style SaaS "
            "for 500 - 2,000+ users. {Company}'s work on {OneLineAboutCompany} is exactly where I want "
            "to contribute next.\n\n"
            "Relevant highlights:\n"
            "- Full-funnel UX: rebuilt flows and reduced booking/checkout friction by 70%.\n"
            "- Payments + real-time: Stripe + Socket.io in production with 100% payment success.\n"
            "- Performance: shipped under 1.8s page loads across devices at 2,000+ user scale.\n\n"
            "Where I'd add value at {Company}: {CustomRequirement}.\n\n"
            "Resume attached. Would appreciate 15 minutes to explore a fit.\n\n"
            "Best regards,\n"
            "Usairam Saeed\n"
            "saeed.usairam@gmail.com | +92-301-8165385"
        ),
    },
    {
        "id": "T6",
        "name": "Marketing / Media / Creative Tech",
        "use_for": "Marketing & Advertising, Media & Entertainment",
        "subject": "Full Stack + UI/UX Engineer - would love to build for {Company}",
        "body": (
            "Hi {HiringManager},\n\n"
            "Big fan of {Company}'s work on {OneLineAboutCompany}. I'm a Full Stack Engineer "
            "(React, Node.js, MongoDB) with a strong UI/UX background:\n"
            "- 1st place, Web Design Competition at Deenfest 2024.\n"
            "- 3rd place, UI/UX Design Competition at NASCON'24.\n"
            "- Shipped SaaS UI improvements measured at 35% usability uplift across 2,000+ users.\n"
            "- Comfortable end-to-end: React/Node/Mongo + Figma/Adobe XD.\n\n"
            "Specifically for {Company}: {CustomRequirement}.\n\n"
            "Resume attached. If you're hiring for product / platform engineering, I'd love to chat.\n\n"
            "Best regards,\n"
            "Usairam Saeed\n"
            "saeed.usairam@gmail.com | +92-301-8165385\n"
            "LinkedIn | GitHub | Portfolio"
        ),
    },
    {
        "id": "T7",
        "name": "Enterprise / Manufacturing / GovTech / GreenTech",
        "use_for": "Construction & Manufacturing, GovTech, GreenTech",
        "subject": "Full Stack Engineer - internal platforms and dashboards",
        "body": (
            "Hi {HiringManager},\n\n"
            "I'm Usairam Saeed, a Full Stack Engineer (React, Node.js, MongoDB) building "
            "production SaaS and internal platforms. {Company}'s work on {OneLineAboutCompany} caught "
            "my attention and I'd like to contribute.\n\n"
            "What I bring:\n"
            "- Clean, modern dashboards built with React + Node + Mongo.\n"
            "- Experience integrating with external APIs, payments and real-time feeds.\n"
            "- DevOps exposure: Docker, Kubernetes, Jenkins, Git-based CI.\n"
            "- Delivered 95% reductions in manual processes via automation (Neuro Mark AI HR SaaS).\n\n"
            "For {Company} specifically: {CustomRequirement}.\n\n"
            "Resume attached. Open to a short call whenever convenient.\n\n"
            "Best regards,\n"
            "Usairam Saeed\n"
            "saeed.usairam@gmail.com | +92-301-8165385"
        ),
    },
    {
        "id": "T8",
        "name": "Cybersecurity",
        "use_for": "Cybersecurity",
        "subject": "Full Stack Engineer for security tooling - {Company}",
        "body": (
            "Hi {HiringManager},\n\n"
            "I've been following {Company}'s work on {OneLineAboutCompany}. I'm a Full Stack "
            "Engineer (React, Node.js, MongoDB) interested in building the front-end / platform side "
            "of security products - dashboards, SIEM-like interfaces, portals, and admin tooling.\n\n"
            "Relevant strengths:\n"
            "- Production React/Node SaaS used by 500 - 2,000+ users.\n"
            "- Data-heavy UI / dashboards with measurable UX improvements.\n"
            "- Comfortable with authentication flows, role-based access, and audit logging.\n"
            "- Docker / Kubernetes / CI familiarity.\n\n"
            "Applied to {Company}: {CustomRequirement}.\n\n"
            "Resume attached. Happy to jump on a 15-minute call.\n\n"
            "Best regards,\n"
            "Usairam Saeed\n"
            "saeed.usairam@gmail.com | +92-301-8165385"
        ),
    },
    {
        "id": "T9",
        "name": "Follow-up (after 5-7 days, no reply)",
        "use_for": "Follow-up",
        "subject": "Following up - {Company} full-stack role",
        "body": (
            "Hi {HiringManager},\n\n"
            "Just floating this back to the top of your inbox in case it got buried. I sent a note last week "
            "about a full-stack / product-engineering role at {Company}.\n\n"
            "Quick recap of the fit:\n"
            "- React + Node.js + MongoDB production SaaS at 500 - 2,000+ user scale.\n"
            "- Payments (Stripe), real-time (Socket.io), scheduling, AI/ML in production.\n"
            "- UX-focused engineer - measured 35% usability improvements.\n\n"
            "Happy to send more detail or hop on a short call whenever convenient.\n\n"
            "Thanks,\n"
            "Usairam Saeed\n"
            "saeed.usairam@gmail.com"
        ),
    },
    {
        "id": "T10",
        "name": "Referral request (warm intro)",
        "use_for": "Referral",
        "subject": "Quick intro request - {Company} role",
        "body": (
            "Hi {ContactName},\n\n"
            "Hope you're doing well. I saw you're at {Company} and wanted to reach out - I'm applying for "
            "full-stack / product-engineering roles there and would really appreciate a quick intro to the "
            "hiring team if you feel comfortable.\n\n"
            "Short version of my background:\n"
            "- Full Stack Engineer (React, Node.js, MongoDB) building production SaaS for 500 - 2,000+ users.\n"
            "- Shipped payments (Stripe), real-time systems (Socket.io), scheduling, and AI-integrated HR SaaS.\n"
            "- Strong UI/UX bent - 35% measurable UX uplift, multiple design-competition wins.\n\n"
            "I've attached my resume. Totally fine if it's not the right time - just thought I'd ask.\n\n"
            "Thanks a lot,\n"
            "Usairam Saeed\n"
            "saeed.usairam@gmail.com | +92-301-8165385"
        ),
    },
]


# Map each vertical to its best-fit template id (see EMAIL_TEMPLATES above).
VERTICAL_TO_TEMPLATE = {
    "Finance/FinTech":              "T3",
    "Healthcare/HealthTech":        "T4",
    "Education & Training":         "T4",
    "Travel & Hospitality":         "T5",
    "E-Commerce & Retail":          "T5",
    "Food & Agriculture":           "T5",
    "Aviation & Logistics":         "T5",
    "Marketing & Advertising":      "T6",
    "Media & Entertainment":        "T6",
    "Construction & Manufacturing": "T7",
    "GovTech":                      "T7",
    "GreenTech":                    "T7",
    "Cybersecurity":                "T8",
    "AI & Data Science":            "T2",
}

DEFAULT_TEMPLATE_ID = "T1"


def get_template(template_id):
    """Return the template dict for a given id (raises KeyError if missing)."""
    for template in EMAIL_TEMPLATES:
        if template["id"] == template_id:
            return template
    raise KeyError(f"Unknown template id: {template_id}")


def pick_template_for_vertical(vertical):
    """Return the template dict best suited to this vertical."""
    template_id = VERTICAL_TO_TEMPLATE.get(vertical, DEFAULT_TEMPLATE_ID)
    return get_template(template_id)


def render(template, context):
    """
    Fill placeholders safely. Missing keys are left as-is so a partial
    context never crashes the sender.
    """
    safe_context = {
        "HiringManager": "Hiring Team",
        "ContactName":   "there",
        "Company":       "your team",
        "Vertical":      "",
        "OneLineAboutCompany": "the work your team is doing",
        "CustomRequirement":   "full-stack product engineering with React / Node.js / MongoDB",
    }
    safe_context.update({k: (v or safe_context.get(k, "")) for k, v in context.items()})

    subject = template["subject"]
    body = template["body"]
    for key, value in safe_context.items():
        subject = subject.replace("{" + key + "}", str(value))
        body = body.replace("{" + key + "}", str(value))
    return subject, body
