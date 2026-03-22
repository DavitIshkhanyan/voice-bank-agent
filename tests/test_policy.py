import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "services/retrieval-api"))

from app.policy import classify_topic


def test_classify_credits_armenian():
    assert classify_topic("Ինչ վարկային տարբերակներ ունեք?") == "credits"


def test_classify_deposits_english():
    assert classify_topic("Tell me about your deposit rates") == "deposits"


def test_classify_branch_locations_armenian():
    assert classify_topic("Մոտակա մասնաճյուղի հասցեն ասա") == "branch_locations"


def test_classify_out_of_scope():
    assert classify_topic("Who is the president of Armenia?") is None

