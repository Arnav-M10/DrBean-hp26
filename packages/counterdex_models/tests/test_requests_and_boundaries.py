import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
EXAMPLES = PACKAGE / "examples"
sys.path.insert(0, str(PACKAGE))

from counterdex_models import ModelError, default_registry, run_request  # noqa: E402


def load(name):
    return json.loads((EXAMPLES / "requests" / f"{name}.request.json").read_text(encoding="utf-8"))


def cli(*args, cwd=None, extra_path=()):
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": os.pathsep.join([str(PACKAGE), *map(str, extra_path)])}
    return subprocess.run([sys.executable, "-B", "-m", "counterdex_models", *args],
                          capture_output=True, text=True, env=env, cwd=cwd, timeout=120)


class RequestTests(unittest.TestCase):
    def test_hard_allowances_are_refused_anywhere_in_a_request(self):
        request = load("fit_full")
        request["noise"]["hard_allowance"] = 0.5
        with self.assertRaises(ModelError) as caught:
            run_request(request, default_registry())
        self.assertEqual(caught.exception.code, "hard_allowance_not_accepted")
        rows = load("fit_full")
        rows["observations"]["rows"][0]["epsilon_allowance"] = "1/2"
        with self.assertRaises(ModelError):
            run_request(rows, default_registry())

    def test_unknown_fields_models_and_schemas_are_refused(self):
        for mutate in (lambda r: r.update(extra=1), lambda r: r.update(models=["plasma.unregistered"]),
                       lambda r: r.update(schema_version="v0"), lambda r: r.update(analysis="prove"),
                       lambda r: r["noise"].update(variance=1)):
            request = load("fit_full")
            mutate(request)
            with self.assertRaises(ModelError):
                run_request(request, default_registry())

    def test_exact_rational_strings_are_accepted_as_binary64(self):
        request = load("fit_full")
        request["observations"]["rows"][0]["value"] = "6575/1000"
        request["noise"]["absolute_sd"] = "1/20"
        result = run_request(request, default_registry())
        self.assertEqual(result["fits"][0]["rows"][0]["observed"], 6.575)
        self.assertEqual(result["certification"], "none")

    def test_digests_cover_request_and_result(self):
        first = run_request(load("grid_ranking"), default_registry())
        second = run_request(load("grid_ranking"), default_registry())
        self.assertEqual(first["result_sha256"], second["result_sha256"])
        self.assertEqual(len(first["request_sha256"]), 64)


class ExampleTests(unittest.TestCase):
    def test_build_script_reproduces_the_committed_examples(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, str(EXAMPLES / "build_examples.py"), tmp], check=True, capture_output=True, timeout=120)
            for path in sorted(Path(tmp).rglob("*.json")):
                committed = EXAMPLES / path.relative_to(tmp)
                self.assertEqual(path.read_bytes(), committed.read_bytes(), str(committed))

    def test_demonstrated_findings(self):
        registry = default_registry()
        early = run_request(load("fit_early"), registry)
        self.assertEqual(early["preferred_model"], "public.single-exponential")
        chi = {f["model"]["id"]: f["chi_square"] for f in early["fits"]}
        self.assertLess(chi["public.two-exponential-mixture"], chi["public.single-exponential"])  # closer fit, not preferred
        self.assertEqual(run_request(load("fit_full"), registry)["preferred_model"], "public.two-exponential-mixture")
        grid = run_request(load("grid_ranking"), registry)
        self.assertEqual(grid["ranked_times"][0], 8)
        mixture = lambda r: next(c for c in r["candidates"] if c["model_id"] == "public.two-exponential-mixture")["selection_frequency"]
        before, after = run_request(load("monte_carlo_early"), registry), run_request(load("monte_carlo_early_plus_8h"), registry)
        self.assertLess(mixture(before), 0.5)
        self.assertGreater(mixture(after), 0.9)
        self.assertFalse(run_request(load("scenarios"), registry)["preferred_model_stable"])

    def test_every_result_disclaims_proof_and_certification(self):
        registry = default_registry()
        for path in sorted((EXAMPLES / "requests").glob("*.json")):
            result = run_request(json.loads(path.read_text(encoding="utf-8")), registry)
            self.assertEqual(result["certification"], "none", path.name)
            self.assertEqual(result["runtime"]["provider_calls"], 0)
            self.assertRegex(result["interpretation"], r"\bnot\b", path.name)


class CommandLineTests(unittest.TestCase):
    def test_run_writes_new_output_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "fit.json"
            done = cli("run", str(EXAMPLES / "requests" / "fit_full.request.json"), "--output", str(out))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(json.loads(out.read_text())["preferred_model"], "public.two-exponential-mixture")
            again = cli("run", str(EXAMPLES / "requests" / "fit_full.request.json"), "--output", str(out))
            self.assertEqual(again.returncode, 2)
            self.assertIn("output_exists", again.stderr)

    def test_operator_registry_adds_a_model_and_requests_can_use_it(self):
        listed = cli("--registry", "registry_plugin:registry", "models", extra_path=[EXAMPLES])
        self.assertEqual(listed.returncode, 0, listed.stderr)
        ids = [m["id"] for m in json.loads(listed.stdout)["models"]]
        self.assertIn("example.exponential-plus-baseline", ids)
        request = load("fit_full")
        request["models"] = ["public.single-exponential", "example.exponential-plus-baseline"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            path.write_text(json.dumps(request))
            done = cli("--registry", "registry_plugin:registry", "run", str(path), extra_path=[EXAMPLES])
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(len(json.loads(done.stdout)["fits"]), 2)
            refused = cli("run", str(path))
            self.assertEqual(refused.returncode, 2)
            self.assertIn("unknown_model", refused.stderr)


class SeparationTests(unittest.TestCase):
    def test_numerical_module_imports_neither_the_exact_checker_nor_network_code(self):
        probe = ("import sys, json; import counterdex_models as m; "
                 "m.run_request(json.load(open(sys.argv[1])), m.default_registry()); "
                 "print(json.dumps(sorted(k for k in sys.modules if k.split('.')[0] in "
                 "('counterdex','socket','ssl','http','urllib','requests','numpy','scipy'))))")
        done = subprocess.run([sys.executable, "-c", probe, str(EXAMPLES / "requests" / "fit_full.request.json")],
                              capture_output=True, text=True, env={"PYTHONPATH": str(PACKAGE)}, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), [])

    def test_published_counterdex_0_3_0_source_identity_is_unchanged(self):
        # Mirrors counterdex.identity without importing it: replay of every 0.3.0
        # artifact requires this exact top-level source manifest.
        root = REPO / "packages" / "groundwork_adapter"
        files = [{"file": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted((root / "counterdex").glob("*.py"))]
        bundle = json.loads((root / "fixtures" / "checked_success.bundle.json").read_text(encoding="utf-8"))
        recorded = bundle["implementation"]
        self.assertEqual(recorded["adapter_version"], "0.3.0")
        self.assertEqual([f["file"] for f in recorded["source_manifest"]], [f["file"] for f in files])
        self.assertEqual(recorded["source_manifest"], files)
        self.assertIn('version = "0.3.0"', (root / "pyproject.toml").read_text())
        self.assertIn("dependencies = []", (root / "pyproject.toml").read_text())


if __name__ == "__main__":
    unittest.main()
