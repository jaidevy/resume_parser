"""
LLM Prompt Evaluation Suite.

Evaluates the quality and reliability of the resume extraction prompt
across a corpus of test resumes. Measures accuracy, consistency,
and coverage of extracted fields.
"""
import json
import os
import sys
import time
from datetime import datetime
from typing import Optional

# Force UTF-8 output on Windows (avoids cp1252 emoji crash)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "resume_parser.settings")

import django
django.setup()

from api.services.extractor import ResumeExtractor, EXTRACTION_SYSTEM_PROMPT, EXTRACTION_SCHEMA


# ── Test Resumes with Expected Values ────────────────────────────────────────

TEST_CASES = [
    {
        "id": "TC001",
        "name": "Standard Software Engineer Resume",
        "text": """
John Michael Doe
Senior Software Engineer

Contact: john.doe@techmail.com | +1-415-555-1234
Location: San Francisco, CA, USA
LinkedIn: https://linkedin.com/in/johndoe
GitHub: https://github.com/johndoe

PROFESSIONAL SUMMARY
Experienced software engineer with 8 years of experience in full-stack development.

SKILLS
Python, Django, React, AWS, Docker, PostgreSQL, Redis, Git

WORK EXPERIENCE

TechCorp Inc. — Senior Software Engineer
January 2020 – Present
Led microservices architecture redesign.

StartupXYZ — Junior Developer
June 2016 – December 2019
Built web applications using Django.

EDUCATION
M.S. Computer Science, Stanford University, 2016
B.Tech Information Technology, IIT Delhi, 2014

CERTIFICATIONS
AWS Solutions Architect Associate
        """,
        "expected": {
            "candidate_full_name": "John Michael Doe",
            "email_ids": ["john.doe@techmail.com"],
            "phones": ["+1-415-555-1234"],
            "current_location": "San Francisco, CA, USA",
            "key_skills_contains": ["Python", "Django", "React", "AWS"],
            "work_experience_count": 2,
            "education_count": 2,
            "has_linkedin": True,
            "has_github": True,
            "gender": "",  # Should NOT infer gender
        },
    },
    {
        "id": "TC002",
        "name": "Multiple Emails and Phones",
        "text": """
Priya Sharma
Data Analyst

Email: priya.sharma@gmail.com, priya.s@company.org
Phone: +91-98765-43210 | +91-11-2345-6789

Location: Mumbai, Maharashtra, India

Gender: Female

SKILLS
Python, R, SQL, Tableau, Power BI, Excel, Machine Learning

EXPERIENCE
DataCo Analytics — Senior Data Analyst
April 2019 – Present
Analyzed large datasets and created dashboards.

InfoTech Solutions — Data Analyst
Jan 2016 – March 2019
Built ETL pipelines and reports.

EDUCATION
M.Sc. Statistics, University of Mumbai, 2015
B.Sc. Mathematics, Delhi University, 2013
        """,
        "expected": {
            "candidate_full_name": "Priya Sharma",
            "email_ids": ["priya.sharma@gmail.com", "priya.s@company.org"],
            "email_count_min": 2,
            "phone_count_min": 1,
            "current_location": "Mumbai",
            "gender": "Female",
            "work_experience_count": 2,
            "education_count": 2,
        },
    },
    {
        "id": "TC003",
        "name": "Minimal Resume - Missing Fields",
        "text": """
Alex Johnson
alex.j@email.com

Web Developer
3 years experience in JavaScript and Node.js
        """,
        "expected": {
            "candidate_full_name": "Alex Johnson",
            "email_ids": ["alex.j@email.com"],
            "phones": [],
            "gender": "",
            "has_linkedin": False,
        },
    },
    {
        "id": "TC004",
        "name": "Resume with Projects and Certifications",
        "text": """
Maria Garcia
Full Stack Developer

Email: maria.garcia@dev.com
Phone: +1 (312) 555-8901
Location: Chicago, IL

SKILLS
JavaScript, TypeScript, React, Node.js, Express, MongoDB, Docker, Kubernetes

EXPERIENCE
WebDev Corp — Full Stack Developer
May 2020 – Present
Developed e-commerce platform serving 1M+ users.

EDUCATION
Bachelor of Science in Computer Science
University of Illinois, 2020

CERTIFICATIONS
Google Cloud Professional Developer
Docker Certified Associate

PROJECTS
E-Commerce Platform - Full-stack e-commerce solution
Technologies: React, Node.js, MongoDB
TaskManager Pro - Project management tool
Technologies: TypeScript, Express, PostgreSQL
        """,
        "expected": {
            "candidate_full_name": "Maria Garcia",
            "email_ids": ["maria.garcia@dev.com"],
            "phone_count_min": 1,
            "work_experience_count": 1,
            "certification_count_min": 2,
            "project_count_min": 2,
        },
    },
    {
        "id": "TC005",
        "name": "Resume with No Clear Sections",
        "text": """
Robert Chen | robert.chen@mail.com | 555-234-5678

I am a marketing specialist with 5 years of experience in digital marketing,
SEO, content strategy, and social media management. I have worked at BrandCo
(2020-Present) and MarketingPro (2018-2020). I hold a BA in Marketing from
NYU (2018). Skills include Google Analytics, HubSpot, SEMrush, Mailchimp.

LinkedIn: https://linkedin.com/in/robertchen
        """,
        "expected": {
            "candidate_full_name": "Robert Chen",
            "email_ids": ["robert.chen@mail.com"],
            "phone_count_min": 1,
            "has_linkedin": True,
        },
    },
]


class PromptEvaluator:
    """
    Evaluates LLM prompt accuracy for resume extraction.

    Metrics:
    - Field-level accuracy (exact match, partial match)
    - Coverage (what % of fields are extracted)
    - Consistency (do repeated runs produce same output)
    - Compliance (gender not inferred, no fabricated data)
    """

    def __init__(self):
        self.extractor = ResumeExtractor()
        self.results = []

    def run_evaluation(self, test_cases=None) -> dict:
        """
        Run evaluation across all test cases.

        Returns:
            dict: Evaluation summary with per-case and aggregate scores
        """
        if test_cases is None:
            test_cases = TEST_CASES

        self.results = []
        total_score = 0
        total_checks = 0

        print(f"\n{'='*70}")
        print("RESUME EXTRACTION PROMPT EVALUATION")
        print(f"{'='*70}")
        print(f"Test Cases: {len(test_cases)}")
        print(f"Extraction Method: {'LLM' if self.extractor.client else 'Regex Fallback'}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print(f"{'='*70}\n")

        for tc in test_cases:
            print(f"\n--- Test Case: {tc['id']} - {tc['name']} ---")
            start_time = time.time()

            extracted = self.extractor.extract(tc["text"])
            elapsed = time.time() - start_time

            score, checks, details = self._evaluate_case(tc, extracted)
            total_score += score
            total_checks += checks

            case_result = {
                "test_case_id": tc["id"],
                "test_case_name": tc["name"],
                "score": score,
                "total_checks": checks,
                "accuracy": score / checks if checks > 0 else 0,
                "elapsed_seconds": elapsed,
                "details": details,
                "extracted_data": extracted,
            }
            self.results.append(case_result)

            print(f"  Score: {score}/{checks} ({case_result['accuracy']:.0%})")
            print(f"  Time: {elapsed:.2f}s")
            for detail in details:
                status = "✅" if detail["passed"] else "❌"
                print(f"  {status} {detail['field']}: {detail['message']}")

        # Aggregate
        overall_accuracy = total_score / total_checks if total_checks > 0 else 0

        summary = {
            "timestamp": datetime.now().isoformat(),
            "method": "llm" if self.extractor.client else "regex_fallback",
            "total_test_cases": len(test_cases),
            "total_checks": total_checks,
            "total_passed": total_score,
            "overall_accuracy": overall_accuracy,
            "meets_threshold": overall_accuracy >= 0.85,
            "threshold": 0.85,
            "per_case_results": self.results,
        }

        print(f"\n{'='*70}")
        print(f"OVERALL ACCURACY: {overall_accuracy:.1%} "
              f"({'PASS' if overall_accuracy >= 0.85 else 'FAIL'} - threshold: 85%)")
        print(f"{'='*70}\n")

        return summary

    def _evaluate_case(self, test_case: dict, extracted: dict) -> tuple:
        """Evaluate a single test case."""
        expected = test_case["expected"]
        score = 0
        total = 0
        details = []

        # Check candidate_full_name
        if "candidate_full_name" in expected:
            total += 1
            if expected["candidate_full_name"].lower() in extracted.get("candidate_full_name", "").lower():
                score += 1
                details.append({"field": "name", "passed": True, "message": f"Matched: {extracted.get('candidate_full_name')}"})
            else:
                details.append({"field": "name", "passed": False, "message": f"Expected '{expected['candidate_full_name']}', got '{extracted.get('candidate_full_name', '')}'"})

        # Check emails
        if "email_ids" in expected:
            total += 1
            expected_emails = set(e.lower() for e in expected["email_ids"])
            extracted_emails = set(e.lower() for e in extracted.get("email_ids", []))
            if expected_emails.issubset(extracted_emails):
                score += 1
                details.append({"field": "emails", "passed": True, "message": f"Found: {extracted.get('email_ids')}"})
            else:
                missing = expected_emails - extracted_emails
                details.append({"field": "emails", "passed": False, "message": f"Missing emails: {missing}"})

        if "email_count_min" in expected:
            total += 1
            if len(extracted.get("email_ids", [])) >= expected["email_count_min"]:
                score += 1
                details.append({"field": "email_count", "passed": True, "message": f"Found {len(extracted.get('email_ids', []))} emails"})
            else:
                details.append({"field": "email_count", "passed": False, "message": f"Expected min {expected['email_count_min']}, found {len(extracted.get('email_ids', []))}"})

        # Check phones
        if "phones" in expected:
            total += 1
            if len(expected["phones"]) == 0 and len(extracted.get("phones", [])) == 0:
                score += 1
                details.append({"field": "phones", "passed": True, "message": "Correctly empty"})
            elif len(expected["phones"]) > 0 and len(extracted.get("phones", [])) > 0:
                score += 1
                details.append({"field": "phones", "passed": True, "message": f"Found: {extracted.get('phones')}"})
            else:
                details.append({"field": "phones", "passed": False, "message": f"Expected {expected['phones']}, got {extracted.get('phones', [])}"})

        if "phone_count_min" in expected:
            total += 1
            if len(extracted.get("phones", [])) >= expected["phone_count_min"]:
                score += 1
                details.append({"field": "phone_count", "passed": True, "message": f"Found {len(extracted.get('phones', []))} phones"})
            else:
                details.append({"field": "phone_count", "passed": False, "message": f"Expected min {expected['phone_count_min']}"})

        # Check gender compliance
        if "gender" in expected:
            total += 1
            extracted_gender = extracted.get("gender", "").strip().lower()
            expected_gender = expected["gender"].strip().lower()
            if extracted_gender == expected_gender:
                score += 1
                details.append({"field": "gender", "passed": True, "message": f"Correct: '{extracted.get('gender', '')}'"})
            else:
                details.append({"field": "gender", "passed": False, "message": f"Expected '{expected['gender']}', got '{extracted.get('gender', '')}'"})

        # Check location
        if "current_location" in expected:
            total += 1
            if expected["current_location"].lower() in extracted.get("current_location", "").lower():
                score += 1
                details.append({"field": "location", "passed": True, "message": f"Found: {extracted.get('current_location')}"})
            else:
                details.append({"field": "location", "passed": False, "message": f"Expected to contain '{expected['current_location']}'"})

        # Check skills
        if "key_skills_contains" in expected:
            total += 1
            extracted_skills = [s.lower() for s in extracted.get("key_skills", [])]
            required = [s.lower() for s in expected["key_skills_contains"]]
            found = sum(1 for s in required if s in extracted_skills)
            if found >= len(required) * 0.5:
                score += 1
                details.append({"field": "skills", "passed": True, "message": f"Found {found}/{len(required)} required skills"})
            else:
                details.append({"field": "skills", "passed": False, "message": f"Only {found}/{len(required)} skills found"})

        # Check work experience count
        if "work_experience_count" in expected:
            total += 1
            actual = len(extracted.get("work_experience", []))
            if actual >= expected["work_experience_count"]:
                score += 1
                details.append({"field": "work_exp_count", "passed": True, "message": f"Found {actual} entries"})
            else:
                details.append({"field": "work_exp_count", "passed": False, "message": f"Expected {expected['work_experience_count']}, found {actual}"})

        # Check education count
        if "education_count" in expected:
            total += 1
            actual = len(extracted.get("education", []))
            if actual >= expected["education_count"]:
                score += 1
                details.append({"field": "edu_count", "passed": True, "message": f"Found {actual} entries"})
            else:
                details.append({"field": "edu_count", "passed": False, "message": f"Expected {expected['education_count']}, found {actual}"})

        # Check URLs
        if "has_linkedin" in expected:
            total += 1
            has = bool(extracted.get("linkedin_url", "").strip())
            if has == expected["has_linkedin"]:
                score += 1
                details.append({"field": "linkedin", "passed": True, "message": f"Present: {has}"})
            else:
                details.append({"field": "linkedin", "passed": False, "message": f"Expected present={expected['has_linkedin']}"})

        if "has_github" in expected:
            total += 1
            has = bool(extracted.get("github_url", "").strip())
            if has == expected["has_github"]:
                score += 1
                details.append({"field": "github", "passed": True, "message": f"Present: {has}"})
            else:
                details.append({"field": "github", "passed": False, "message": f"Expected present={expected['has_github']}"})

        # Check certifications
        if "certification_count_min" in expected:
            total += 1
            actual = len(extracted.get("certifications", []))
            if actual >= expected["certification_count_min"]:
                score += 1
                details.append({"field": "certifications", "passed": True, "message": f"Found {actual}"})
            else:
                details.append({"field": "certifications", "passed": False, "message": f"Expected min {expected['certification_count_min']}, found {actual}"})

        # Check projects
        if "project_count_min" in expected:
            total += 1
            actual = len(extracted.get("projects", []))
            if actual >= expected["project_count_min"]:
                score += 1
                details.append({"field": "projects", "passed": True, "message": f"Found {actual}"})
            else:
                details.append({"field": "projects", "passed": False, "message": f"Expected min {expected['project_count_min']}, found {actual}"})

        return score, total, details

    def run_consistency_test(self, text: str, runs: int = 3) -> dict:
        """
        Test extraction consistency by running the same input multiple times.

        Returns:
            dict: Consistency metrics
        """
        results = []
        for i in range(runs):
            extracted = self.extractor.extract(text)
            results.append(extracted)

        # Compare key fields across runs
        names = [r.get("candidate_full_name", "") for r in results]
        emails = [tuple(sorted(r.get("email_ids", []))) for r in results]

        consistency = {
            "runs": runs,
            "name_consistent": len(set(names)) == 1,
            "email_consistent": len(set(emails)) == 1,
            "all_consistent": len(set(names)) == 1 and len(set(emails)) == 1,
        }

        return consistency

    def export_results(self, filepath: str = "evaluation_results.json"):
        """Export evaluation results to JSON file."""
        with open(filepath, "w") as f:
            json.dump(self.results, f, indent=2, default=str)
        print(f"Results exported to: {filepath}")


def run_prompt_evaluation():
    """Entry point for running the full prompt evaluation."""
    evaluator = PromptEvaluator()
    summary = evaluator.run_evaluation()
    evaluator.export_results(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "prompt_evaluation_results.json",
        )
    )
    return summary


if __name__ == "__main__":
    run_prompt_evaluation()
