"""Masking tests — synthetic pinned set (public-safe shapes of pilot v1).

The pilot's real pinned set is operator data and never enters the repo;
these cases reproduce its shapes with invented values: the partial-span
handle, the parenthesized phone, the domain-vocabulary keep-set.
"""

import unittest

from gated_dispatch.masking import Masker, MaskingError, Register, Vault


def make_masker(detectors=()):
    reg = Register(
        names={"Asha Rao": "SPOUSE", "Dev Patel": "BROTHER"},
        name_parts={"Asha": "SPOUSE", "Rao": "SPOUSE", "Dev": "BROTHER"},
        orgs={"Acme Corp": "EMPLOYER", "Globex": "VENDOR"},
        always=["Project Nightingale"],
        never={"purnima", "thirumanjanam", "austin", "texas"},
    )
    return Masker(reg, detectors=detectors)


class MaskingTest(unittest.TestCase):
    def setUp(self):
        self.masker = make_masker()
        self.vault = Vault("GD-TEST-0001")

    def test_name_to_role_token_and_roundtrip(self):
        masked = self.masker.mask("Send the draft to Asha Rao before noon.", self.vault)
        self.assertNotIn("Asha Rao", masked)
        self.assertIn("[SPOUSE_1]", masked)
        self.assertEqual(self.masker.reidentify(masked, self.vault),
                         "Send the draft to Asha Rao before noon.")

    def test_gazetteer_catches_handle_form(self):
        # the pilot's partial-span case: asha.r must not survive
        masked = self.masker.mask("Files for asha.r are in the folder.", self.vault)
        self.assertNotIn("asha", masked.lower())

    def test_parenthesized_phone_masked(self):
        # the pilot's Rampart miss shape, owned by the deterministic layer
        masked = self.masker.mask("Call (214) 555-0147 after ten.", self.vault)
        self.assertNotIn("555-0147", masked)

    def test_card_requires_luhn(self):
        good = self.masker.mask("Card 4242 4242 4242 4242 on file.", self.vault)
        self.assertNotIn("4242", good)
        bad = self.masker.mask("Ref 1234 5678 9012 3456 noted.", Vault("GD-TEST-0002"))
        self.assertIn("1234 5678 9012 3456", bad)

    def test_ssn_structural_rules(self):
        masked = self.masker.mask("SSN 123-45-6789 as a sample.", self.vault)
        self.assertNotIn("123-45-6789", masked)
        kept = self.masker.mask("ZIP+4 123-45-6789 is not this.", Vault("GD-TEST-0003"))
        # 123-45-6789 has valid SSN structure; the reserved-area case differs:
        masked2 = self.masker.mask("Area 666-45-6789 is reserved.", Vault("GD-TEST-0004"))
        self.assertIn("666-45-6789", masked2)

    def test_org_class_token(self):
        masked = self.masker.mask("The Acme Corp engagement runs via Globex.", self.vault)
        self.assertNotIn("Acme Corp", masked)
        self.assertIn("[EMPLOYER_1]", masked)
        self.assertIn("[VENDOR_1]", masked)

    def test_always_tokenize(self):
        masked = self.masker.mask("Project Nightingale kicks off Monday.", self.vault)
        self.assertNotIn("Nightingale", masked)

    def test_keep_set_survives(self):
        text = "Thirumanjanam falls on Purnima in Austin, Texas."
        masked = self.masker.mask(text, self.vault)
        self.assertEqual(masked, text)

    def test_known_value_sweep_remasks_later_block(self):
        self.masker.mask("Asha Rao called.", self.vault)
        masked = self.masker.mask("Following up: Asha Rao confirmed.", self.vault)
        self.assertNotIn("Asha Rao", masked)

    def test_leak_scan_quarantines(self):
        self.masker.mask("Asha Rao called.", self.vault)
        leaks = self.masker.leak_scan("As Asha Rao noted, approved.", self.vault)
        self.assertIn("Asha Rao", leaks)
        clean = self.masker.leak_scan("As [SPOUSE_1] noted, approved.", self.vault)
        self.assertEqual(clean, [])

    def test_detector_seam_and_never_guard(self):
        def fake_detector(text):
            i = text.lower().find("purnima")
            return [(i, i + 7, "NAME")] if i >= 0 else []
        masker = make_masker(detectors=[fake_detector])
        masked = masker.mask("Purnima is Friday.", Vault("GD-TEST-0005"))
        self.assertIn("Purnima", masked)  # never-mask beats the detector

    def test_fail_closed_on_detector_error(self):
        def broken(text):
            raise RuntimeError("engine down")
        masker = make_masker(detectors=[broken])
        with self.assertRaises(MaskingError):
            masker.mask("Anything at all.", Vault("GD-TEST-0006"))

    def test_counts_are_class_only(self):
        self.masker.mask("Asha Rao at Acme Corp, card 4242 4242 4242 4242.", self.vault)
        self.assertEqual(self.vault.counts.get("name"), 1)
        self.assertEqual(self.vault.counts.get("org"), 1)
        self.assertEqual(self.vault.counts.get("identifier"), 1)
        for value in self.vault.counts.values():
            self.assertIsInstance(value, int)


if __name__ == "__main__":
    unittest.main()
