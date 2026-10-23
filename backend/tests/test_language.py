"""Unit tests for the Tamil / Tanglish / English command understanding."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import language as lang


class LanguageDetectionTests(unittest.TestCase):
    def test_detects_tamil_script(self):
        self.assertEqual(lang.detect_language("எனது திட்ட விவரங்களை சேமி"), lang.LANG_TAMIL)

    def test_detects_tanglish(self):
        self.assertEqual(lang.detect_language("En project deadline Friday."), lang.LANG_TANGLISH)
        self.assertEqual(lang.detect_language("Enna nyabagam vechirukka?"), lang.LANG_TANGLISH)

    def test_detects_english(self):
        self.assertEqual(lang.detect_language("What do you remember?"), lang.LANG_ENGLISH)

    def test_mode_normalisation(self):
        self.assertEqual(lang.normalize_mode("ta-IN"), lang.MODE_TAMIL)
        self.assertEqual(lang.normalize_mode("Tamil"), lang.MODE_TAMIL)
        self.assertEqual(lang.normalize_mode("tanglish"), lang.MODE_TANGLISH)
        self.assertEqual(lang.normalize_mode("en-IN"), lang.MODE_ENGLISH)
        self.assertEqual(lang.normalize_mode(None), lang.MODE_ENGLISH)
        self.assertEqual(lang.normalize_mode("nonsense"), lang.MODE_ENGLISH)


class NormalisationTests(unittest.TestCase):
    def test_tanglish_save_command_is_detected(self):
        analysis = lang.analyze("Naan sonna project details save pannu.")
        self.assertEqual(analysis.intent, "save")
        self.assertEqual(analysis.content, "project details")

    def test_tamil_script_save_command_is_detected(self):
        analysis = lang.analyze("எனது திட்ட விவரங்களை சேமி")
        self.assertEqual(analysis.intent, "save")
        self.assertIn("திட்ட", analysis.content)

    def test_english_save_command_keeps_original_wording(self):
        analysis = lang.analyze("Remember that my project deadline is Friday")
        self.assertEqual(analysis.intent, "save")
        self.assertEqual(analysis.content, "my project deadline is Friday")

    def test_normalisation_keeps_names_dates_and_numbers(self):
        analysis = lang.analyze("Save Priya's birthday on 12-05 to memory")
        self.assertEqual(analysis.intent, "save")
        self.assertIn("Priya", analysis.content)
        self.assertIn("12-05", analysis.content)

    def test_canonical_form_rewrites_only_command_phrases(self):
        canonical = lang.canonicalize("En project deadline Friday save pannu.")
        self.assertIn("save", canonical)
        self.assertIn("project deadline Friday", canonical)

    def test_canonical_form_leaves_names_intact(self):
        canonical = lang.canonicalize("Save Priya's birthday on 12-05 to memory")
        self.assertIn("Priya", canonical)
        self.assertIn("12-05", canonical)


class IntentTests(unittest.TestCase):
    def test_statement_is_not_a_save_command(self):
        analysis = lang.analyze("En project deadline Friday.")
        self.assertEqual(analysis.intent, "statement")
        self.assertFalse(analysis.needs_clarification)

    def test_greeting_is_not_a_save_command(self):
        analysis = lang.analyze("Enna nyabagam vechirukka?")
        self.assertEqual(analysis.intent, "greeting")

    def test_question_is_not_a_save_command(self):
        analysis = lang.analyze("What is my secret project?")
        self.assertEqual(analysis.intent, "statement")
        self.assertTrue(analysis.is_question)

    def test_list_intents(self):
        self.assertEqual(lang.analyze("What do you remember?").intent, "list")
        self.assertEqual(lang.analyze("En memories enna irukku?").intent, "list")

    def test_reminder_list_intent(self):
        analysis = lang.analyze("En reminders enna irukku?")
        self.assertEqual(analysis.intent, "reminder_list")

    def test_reminder_create_intent(self):
        analysis = lang.analyze("Remind me to call mom tomorrow")
        self.assertEqual(analysis.intent, "reminder_create")
        self.assertEqual(analysis.title, "call mom")
        self.assertEqual(analysis.due, "tomorrow")

    def test_search_intent(self):
        analysis = lang.analyze("En project details kidaikkum?")
        self.assertEqual(analysis.intent, "search")
        self.assertEqual(analysis.query, "project details")


class AmbiguityTests(unittest.TestCase):
    def test_delete_with_generic_target_is_ambiguous(self):
        analysis = lang.analyze("Intha memory delete pannu.")
        self.assertEqual(analysis.intent, "delete")
        self.assertTrue(analysis.needs_clarification)
        self.assertEqual(analysis.clarification, "ambiguous_target")

    def test_delete_with_specific_target_is_unambiguous(self):
        analysis = lang.analyze("Delete the memory about project deadline")
        self.assertEqual(analysis.intent, "delete")
        self.assertFalse(analysis.needs_clarification)
        self.assertIn("project deadline", analysis.target)

    def test_delete_bulk_target_is_treated_as_ambiguous(self):
        analysis = lang.analyze("Delete all my memories")
        self.assertTrue(analysis.needs_clarification)

    def test_save_without_content_needs_clarification(self):
        analysis = lang.analyze("Save pannu")
        self.assertEqual(analysis.intent, "save")
        self.assertTrue(analysis.needs_clarification)
        self.assertEqual(analysis.clarification, "empty_content")

    def test_ambiguous_numeric_date_needs_clarification(self):
        analysis = lang.analyze("Remember the meeting on 05/11")
        self.assertTrue(analysis.needs_clarification)
        self.assertEqual(analysis.clarification, "ambiguous_date")

    def test_search_without_term_needs_clarification(self):
        analysis = lang.analyze("Find ")
        self.assertEqual(analysis.intent, "search")
        self.assertTrue(analysis.needs_clarification)


class ConfirmationTests(unittest.TestCase):
    def test_yes_is_a_confirmation(self):
        self.assertTrue(lang.is_confirmation("yes"))
        self.assertTrue(lang.is_confirmation("aam"))
        self.assertTrue(lang.is_confirmation("pannunga"))

    def test_no_is_a_rejection(self):
        self.assertTrue(lang.is_negation("no"))
        self.assertTrue(lang.is_negation("thevai"))

    def test_a_real_command_is_not_a_confirmation(self):
        self.assertFalse(lang.is_confirmation("naan project details save pannu"))
        self.assertFalse(lang.is_negation("delete pannu"))


class EmptyInputTests(unittest.TestCase):
    def test_empty_string(self):
        analysis = lang.analyze("")
        self.assertEqual(analysis.intent, "empty")
        self.assertTrue(analysis.is_empty)

    def test_whitespace_only(self):
        analysis = lang.analyze("   \n  ")
        self.assertEqual(analysis.intent, "empty")
        self.assertTrue(analysis.is_empty)


class TamilScriptTests(unittest.TestCase):
    """Tamil uses combining marks, which a plain ``\\w`` regex gets wrong."""

    def test_split_words_keeps_the_pulli_with_its_letter(self):
        self.assertEqual(lang.split_words("இந்த நினைவு"), ["இந்த", "நினைவு"])

    def test_tamil_generic_target_is_ambiguous(self):
        analysis = lang.analyze("இந்த நினைவை நீக்கு")
        self.assertEqual(analysis.intent, "delete")
        self.assertTrue(analysis.needs_clarification)
        self.assertEqual(analysis.clarification, "ambiguous_target")

    def test_tamil_question_is_detected(self):
        analysis = lang.analyze("என் பெயர் என்ன?")
        self.assertTrue(analysis.is_question)
        self.assertEqual(analysis.intent, "statement")

    def test_tamil_possessive_statement_is_not_a_question(self):
        analysis = lang.analyze("என் பெயர் ரமேஷ்")
        self.assertFalse(analysis.is_question)

    def test_tamil_list_phrase(self):
        self.assertEqual(lang.analyze("என்ன நினைவுகள் உள்ளன?").intent, "list")

    def test_tamil_relative_date_is_detected(self):
        analysis = lang.analyze("நாளை குறிப்பு வை")
        self.assertEqual(analysis.intent, "reminder_create")
        self.assertEqual(analysis.due, "நாளை")


class QuestionTopicTests(unittest.TestCase):
    """The topic of a question is used to look up real stored records."""

    def test_english_topic(self):
        self.assertEqual(
            lang.extract_question_topic("What is my project deadline?"),
            "project deadline",
        )

    def test_tamil_topic(self):
        self.assertEqual(lang.extract_question_topic("என் பெயர் என்ன?"), "பெயர்")

    def test_tanglish_topic(self):
        self.assertEqual(lang.extract_question_topic("Project details enna?"), "Project details")

    def test_question_without_a_topic(self):
        self.assertEqual(lang.extract_question_topic("What do you know?"), "")


if __name__ == "__main__":
    unittest.main()
