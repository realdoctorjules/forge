"""Regulatory radar (US FDA) — a DETERMINISTIC, citation-linked considerations
checklist driven by a short questionnaire about intended use.

Deliberately NOT an AI/LLM guess: a confidently-wrong regulatory pathway is
worse than none. This produces preliminary *considerations* with real FDA
citations — never a determination, never legal/regulatory advice.
"""
from __future__ import annotations

QUESTIONS = [
    {"id": "purpose", "label": "What is the device's intended purpose?",
     "options": [
         {"v": "wellness", "l": "General wellness / gadget — no medical claim"},
         {"v": "monitor", "l": "Monitor a physiological parameter or condition"},
         {"v": "diagnose_treat", "l": "Diagnose, treat, or mitigate a disease"},
         {"v": "sustain", "l": "Sustain/support life, or is implanted"}]},
    {"id": "contact", "label": "Does it contact the patient's body?",
     "options": [
         {"v": "none", "l": "No body contact"},
         {"v": "skin", "l": "Intact skin / surface only"},
         {"v": "mucosal", "l": "Mucosal or breached skin (short-term)"},
         {"v": "internal", "l": "Blood path / internal tissue / implant"}]},
    {"id": "powered", "label": "Is it electrically powered or energy-emitting near a person?",
     "options": [{"v": "no", "l": "No"}, {"v": "yes", "l": "Yes"}]},
    {"id": "sterile", "label": "Is it sterile or single-use?",
     "options": [{"v": "no", "l": "No"}, {"v": "yes", "l": "Yes"}]},
]

LINKS = {
    "Classify your device": "https://www.fda.gov/medical-devices/overview-device-regulation/classify-your-medical-device",
    "510(k)": "https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/premarket-notification-510k",
    "De Novo": "https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/de-novo-classification-request",
    "PMA": "https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/premarket-approval-pma",
}


def questions() -> list:
    return QUESTIONS


def assess(answers: dict) -> dict:
    purpose = answers.get("purpose", "wellness")
    contact = answers.get("contact", "none")
    powered = answers.get("powered", "no") == "yes"
    sterile = answers.get("sterile", "no") == "yes"

    medical = purpose in ("monitor", "diagnose_treat", "sustain") or contact in ("mucosal", "internal")

    if not medical and contact == "none":
        cls = "Likely NOT an FDA medical device (consumer product)"
        pathway = ("No FDA device pathway likely. General consumer-product safety (e.g., CPSC) "
                   "and product-liability still apply. Avoid any medical claims, which could "
                   "reclassify it as a device.")
    elif purpose == "sustain" or contact == "internal":
        cls = "Likely Class III (highest risk) — or De Novo if novel"
        pathway = "Premarket Approval (PMA), or a De Novo request if low-to-moderate risk and novel."
    elif purpose == "diagnose_treat" or contact == "mucosal" or powered:
        cls = "Likely Class II (moderate risk)"
        pathway = "Usually 510(k) clearance (substantial equivalence to a predicate), or De Novo."
    else:
        cls = "Likely Class I (lowest risk)"
        pathway = "Often 510(k)-exempt, but still subject to general controls (registration, labeling, QSR)."

    considerations = []
    if contact in ("skin", "mucosal", "internal"):
        considerations.append({
            "title": "Biocompatibility (ISO 10993)",
            "detail": ("Patient-contacting materials need a biocompatibility evaluation. "
                       "3D-printed PLA / PETG / resin are generally NOT biocompatible as-printed "
                       "(residual monomer, porosity, non-medical-grade)."),
            "url": "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/use-international-standard-iso-10993-1-biological-evaluation-medical-devices-part-1-evaluation-and"})
    if powered:
        considerations.append({
            "title": "Electrical safety & EMC (IEC 60601)",
            "detail": "Powered devices used on/near a patient must meet electrical-safety and EMC standards.",
            "url": "https://www.fda.gov/medical-devices/electromagnetic-compatibility-emc-medical-devices"})
    if sterile:
        considerations.append({
            "title": "Sterilization & shelf life",
            "detail": "Validate the sterilization method (e.g., ISO 11135/11137) and packaging integrity / shelf life.",
            "url": "https://www.fda.gov/medical-devices/general-hospital-devices-and-supplies/sterilization-medical-devices"})
    if medical:
        considerations.append({
            "title": "Quality System (21 CFR 820 / QMSR) + UDI",
            "detail": "Marketed devices need a quality system and, usually, Unique Device Identification labeling.",
            "url": "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-820"})
        considerations.append({
            "title": "Clinical testing → IDE + IRB (21 CFR 812)",
            "detail": ("Testing on human subjects before clearance generally requires an "
                       "Investigational Device Exemption and IRB approval — do NOT test a "
                       "non-cleared device on patients without this."),
            "url": "https://www.fda.gov/medical-devices/how-study-and-market-your-device/investigational-device-exemption-ide"})

    return {
        "is_medical_device": medical,
        "class_estimate": cls,
        "pathway": pathway,
        "considerations": considerations,
        "links": LINKS,
        "disclaimer": ("Preliminary considerations only — NOT a regulatory determination and "
                       "NOT legal advice. Confirm classification via the FDA and a qualified "
                       "regulatory professional before any clinical use, sale, or marketing."),
    }
