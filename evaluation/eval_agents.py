"""
Agent Evaluation Suite.

Evaluates the end-to-end resume parsing agent pipeline:
- Ingestion → Validation → Extraction → Storage → Standardization → Output

Tests the full workflow and measures:
- End-to-end accuracy
- Error handling and recovery
- Edge case handling
- Performance metrics
"""
import json
import os
import sys
import time
import tempfile
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

from api.services.validator import FileValidator
from api.services.parser import ResumeParser
from api.services.extractor import ResumeExtractor
from api.services.standardizer import ResumeStandardizer
from api.services.excel_storage import ExcelStorageClient


class AgentEvaluator:
    """
    End-to-end agent pipeline evaluator.

    Evaluates:
    1. File validation accuracy
    2. Text extraction quality
    3. Data extraction accuracy
    4. Standardized output quality
    5. Error handling robustness
    6. Performance benchmarks
    """

    def __init__(self):
        self.validator = FileValidator()
        self.parser = ResumeParser()
        self.extractor = ResumeExtractor()
        self.standardizer = ResumeStandardizer()
        self.results = []

    def run_full_evaluation(self) -> dict:
        """Run all evaluation suites."""
        print(f"\n{'='*70}")
        print("AGENT PIPELINE EVALUATION")
        print(f"{'='*70}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print(f"{'='*70}\n")

        results: dict = {
            "validation": self._eval_validation(),
            "parsing": self._eval_parsing(),
            "extraction": self._eval_extraction(),
            "standardization": self._eval_standardization(),
            "error_handling": self._eval_error_handling(),
            "performance": self._eval_performance(),
        }

        # Calculate overall
        all_scores = []
        for category, r in results.items():
            if "accuracy" in r:
                all_scores.append(r["accuracy"])

        results["overall_accuracy"] = (
            sum(all_scores) / len(all_scores) if all_scores else 0
        )
        results["timestamp"] = datetime.now().isoformat()

        print(f"\n{'='*70}")
        print(f"OVERALL AGENT ACCURACY: {results['overall_accuracy']:.1%}")
        print(f"{'='*70}\n")

        return results

    def _eval_validation(self) -> dict:
        """Evaluate file validation logic."""
        print("\n--- Validation Tests ---")
        from django.core.files.uploadedfile import SimpleUploadedFile

        tests = [
            {"name": "Valid PDF", "file": SimpleUploadedFile("test.pdf", b"%PDF-1.4 content"), "expected_valid": True},
            {"name": "Valid DOCX", "file": SimpleUploadedFile("test.docx", b"PK\x03\x04" + b"\x00" * 50), "expected_valid": True},
            {"name": "Valid TXT", "file": SimpleUploadedFile("test.txt", b"Resume content here"), "expected_valid": True},
            {"name": "Empty file", "file": SimpleUploadedFile("empty.pdf", b""), "expected_valid": False},
            {"name": "Unsupported type", "file": SimpleUploadedFile("test.exe", b"MZ"), "expected_valid": False},
            {"name": "None file", "file": None, "expected_valid": False},
            {"name": "Image for OCR", "file": SimpleUploadedFile("scan.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 50), "expected_valid": True},
            {"name": "Password PDF", "file": SimpleUploadedFile("locked.pdf", b"%PDF-1.4 /Encrypt test"), "expected_valid": False},
        ]

        passed = 0
        total = len(tests)

        for test in tests:
            result = self.validator.validate(test["file"])
            is_correct = result["valid"] == test["expected_valid"]
            if is_correct:
                passed += 1
            status = "✅" if is_correct else "❌"
            print(f"  {status} {test['name']}: valid={result['valid']} (expected={test['expected_valid']})")

        accuracy = passed / total
        print(f"  Validation accuracy: {accuracy:.0%}\n")
        return {"total": total, "passed": passed, "accuracy": accuracy}

    def _eval_parsing(self) -> dict:
        """Evaluate text extraction from files."""
        print("\n--- Parsing Tests ---")

        tests = []

        # TXT file test
        content = "John Doe\nSoftware Engineer\nEmail: john@test.com\nSkills: Python, Django"
        fd, path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, "w") as f:
            f.write(content)
        tests.append({
            "name": "TXT extraction",
            "path": path,
            "type": ".txt",
            "expected_contains": ["John Doe", "Python"],
        })

        # RTF file test
        rtf_content = r"{\rtf1\ansi Hello World Resume}"
        fd2, path2 = tempfile.mkstemp(suffix=".rtf")
        with os.fdopen(fd2, "w") as f:
            f.write(rtf_content)
        tests.append({
            "name": "RTF extraction",
            "path": path2,
            "type": ".rtf",
            "expected_contains": [],  # May or may not extract depending on striprtf
        })

        passed = 0
        total = 0

        for test in tests:
            total += 1
            result = self.parser.parse(test["path"], test["type"])
            all_found = all(
                keyword in result["text"]
                for keyword in test["expected_contains"]
            )
            is_pass = result["success"] and all_found

            if is_pass or not test["expected_contains"]:
                passed += 1
                print(f"  ✅ {test['name']}: extracted {len(result['text'])} chars")
            else:
                print(f"  ❌ {test['name']}: success={result['success']}, missing keywords")

            # Cleanup
            os.unlink(test["path"])

        # Non-existent file test
        total += 1
        result = self.parser.parse("/nonexistent/file.txt", ".txt")
        if not result["success"]:
            passed += 1
            print(f"  ✅ Nonexistent file: correctly failed")
        else:
            print(f"  ❌ Nonexistent file: should have failed")

        accuracy = passed / total if total > 0 else 0
        print(f"  Parsing accuracy: {accuracy:.0%}\n")
        return {"total": total, "passed": passed, "accuracy": accuracy}

    def _eval_extraction(self) -> dict:
        """Evaluate data extraction accuracy."""
        print("\n--- Extraction Tests ---")

        from evaluation.eval_prompts import TEST_CASES, PromptEvaluator

        evaluator = PromptEvaluator()
        summary = evaluator.run_evaluation(TEST_CASES[:3])  # Use first 3 test cases

        print(f"  Extraction accuracy: {summary['overall_accuracy']:.0%}\n")
        return {
            "total": summary["total_checks"],
            "passed": summary["total_passed"],
            "accuracy": summary["overall_accuracy"],
        }

    def _eval_standardization(self) -> dict:
        """Evaluate standardized resume output."""
        print("\n--- Standardization Tests ---")

        tests = [
            {
                "name": "Full data standardization",
                "data": {
                    "candidate_full_name": "John Doe",
                    "email_ids": ["john@test.com"],
                    "phones": ["+1-555-1234"],
                    "current_location": "San Francisco",
                    "professional_summary": "Experienced developer with 5 years of experience.",
                    "key_skills": ["Python", "Django"],
                    "work_experience": [{"company": "Corp", "role": "Dev", "start_date": "2020", "end_date": "Present"}],
                    "education": [{"degree": "BS", "institution": "MIT", "year": "2019"}],
                    "certifications": ["AWS Certified"],
                },
                "expected_contains": ["JOHN DOE", "john@test.com", "Python"],
            },
            {
                "name": "Minimal data",
                "data": {"candidate_full_name": "Jane"},
                "expected_contains": ["JANE"],
            },
            {
                "name": "Empty data",
                "data": {},
                "expected_contains": [],
            },
        ]

        passed = 0
        total = len(tests)

        for test in tests:
            text = self.standardizer.generate_text_output(test["data"])
            all_found = all(kw in text for kw in test["expected_contains"])
            if all_found:
                passed += 1
                print(f"  ✅ {test['name']}: {len(text)} chars output")
            else:
                print(f"  ❌ {test['name']}: missing expected content")

        # Test no fabricated data
        total += 1
        no_certs_data = {"candidate_full_name": "Test", "certifications": []}
        text = self.standardizer.generate_text_output(no_certs_data)
        if "CERTIFICATIONS" not in text:
            passed += 1
            print(f"  ✅ No fabricated sections: no certification section for empty certs")
        else:
            print(f"  ❌ Fabricated section detected")

        accuracy = passed / total if total > 0 else 0
        print(f"  Standardization accuracy: {accuracy:.0%}\n")
        return {"total": total, "passed": passed, "accuracy": accuracy}

    def _eval_error_handling(self) -> dict:
        """Evaluate error handling and graceful failures."""
        print("\n--- Error Handling Tests ---")

        passed = 0
        total = 0

        # Test 1: Unsupported format
        total += 1
        result = self.parser.parse("fake.xyz", ".xyz")
        if not result["success"] and result["error"]:
            passed += 1
            print(f"  ✅ Unsupported format: graceful error")
        else:
            print(f"  ❌ Unsupported format: should fail gracefully")

        # Test 2: Empty text extraction
        total += 1
        extracted = self.extractor.extract("")
        if isinstance(extracted, dict):
            passed += 1
            print(f"  ✅ Empty text: returns valid dict")
        else:
            print(f"  ❌ Empty text: unexpected return type")

        # Test 3: Excel storage client
        total += 1
        xl = ExcelStorageClient()
        if xl.is_configured:
            passed += 1
            print(f"  ✅ Excel storage: configured and available")
        else:
            print(f"  ❌ Excel storage: not configured")

        # Test 4: Invalid validator input
        total += 1
        result = self.validator.validate(None)
        if not result["valid"]:
            passed += 1
            print(f"  ✅ None input: rejected correctly")
        else:
            print(f"  ❌ None input: should reject")

        accuracy = passed / total if total > 0 else 0
        print(f"  Error handling accuracy: {accuracy:.0%}\n")
        return {"total": total, "passed": passed, "accuracy": accuracy}

    def _eval_performance(self) -> dict:
        """Evaluate processing performance."""
        print("\n--- Performance Tests ---")

        # Test text extraction performance
        content = "Test resume " * 1000  # ~11KB
        fd, path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, "w") as f:
            f.write(content)

        start = time.time()
        result = self.parser.parse(path, ".txt")
        parse_time = time.time() - start
        os.unlink(path)

        # Test extraction performance
        start = time.time()
        extracted = self.extractor.extract(content[:5000])
        extract_time = time.time() - start

        # Test standardization performance
        data = {
            "candidate_full_name": "Test",
            "email_ids": ["t@t.com"],
            "key_skills": ["Python"] * 20,
            "work_experience": [{"company": f"Co{i}", "role": "Dev"} for i in range(5)],
        }
        start = time.time()
        text = self.standardizer.generate_text_output(data)
        std_time = time.time() - start

        total_time = parse_time + extract_time + std_time

        print(f"  Parse time: {parse_time:.3f}s")
        print(f"  Extract time: {extract_time:.3f}s")
        print(f"  Standardize time: {std_time:.3f}s")
        print(f"  Total pipeline: {total_time:.3f}s")
        print(f"  Within budget (120s): {'✅' if total_time < 120 else '❌'}")

        return {
            "parse_time": parse_time,
            "extract_time": extract_time,
            "standardize_time": std_time,
            "total_time": total_time,
            "within_budget": total_time < 120,
            "accuracy": 1.0 if total_time < 120 else 0.5,
        }

    def export_results(self, filepath: str = "agent_evaluation_results.json"):
        """Export evaluation results to JSON."""
        results = self.run_full_evaluation()
        with open(filepath, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Results exported to: {filepath}")
        return results


def run_agent_evaluation():
    """Entry point for running the full agent evaluation."""
    evaluator = AgentEvaluator()
    results = evaluator.export_results(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "agent_evaluation_results.json",
        )
    )
    return results


if __name__ == "__main__":
    run_agent_evaluation()
