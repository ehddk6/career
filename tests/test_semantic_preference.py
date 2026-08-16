from career_pipeline.argument_search import SEMANTIC_DIMENSIONS
from career_pipeline.semantic_preference import record_semantic_preference, semantic_preference_weights, compare_and_record

def verdicts(pref="winner", confidence=4):
    return [{"dimension":d,"preference":pref,"confidence":confidence} for d in SEMANTIC_DIMENSIONS]

def test_profile_stores_no_source_text_and_shrinks_single_comparison(tmp_path):
    path=tmp_path/"semantic.json"
    profile=record_semantic_preference(path,verdicts(),winner_label="claude",loser_label="gpt")
    assert profile["privacy"]["stores_source_text"] is False
    assert profile["provider_winners"]["claude"]==1
    weights=semantic_preference_weights(profile)
    assert all(1.0 < x < 1.35 for x in weights.values())

def test_model_explains_known_user_winner_not_choose_it(tmp_path):
    seen={}
    def runner(stage,prompt,model_id,timeout_ms):
        seen["prompt"]=prompt
        return {"dimensions":verdicts("winner",3)}
    compare_and_record(tmp_path/"p.json",winner_text="WIN TEXT",loser_text="LOSE TEXT",
                       model_id="judge",runner=runner)
    assert "already chosen WINNER" in seen["prompt"]
    raw=(tmp_path/"p.json").read_text(encoding="utf-8")
    assert "WIN TEXT" not in raw and "LOSE TEXT" not in raw
