import json
from pathlib import Path

from career_pipeline.writing_preference import (
    load_preference_profile,
    preference_directives,
    preference_distance,
    record_preference,
    style_fingerprint,
)


def test_preference_profile_never_stores_source_text(tmp_path: Path):
    profile_path=tmp_path/'writing_preference.json'
    winner='자료를 보며 이상한 지점을 먼저 찾았습니다. 숫자보다 원자료의 흐름을 따라가니 원인이 보였습니다. 그래서 필요한 부분만 고쳤습니다.'
    loser='먼저 자료를 확인했습니다. 또한 내용을 대조했습니다. 이를 통해 결과를 기록하고 보고했습니다. 적극적으로 기여하겠습니다.'
    profile=record_preference(
        profile_path,
        winner_text=winner,
        loser_text=loser,
        winner_label='claude',
        loser_label='gpt',
    )
    raw=profile_path.read_text(encoding='utf-8')
    assert winner not in raw
    assert loser not in raw
    assert profile['comparison_count']==1
    assert profile['privacy']['stores_source_text'] is False
    assert profile['winner_labels']['claude']==1
    assert preference_directives(profile)


def test_preference_distance_favors_winner_like_structure(tmp_path: Path):
    profile_path=tmp_path/'writing_preference.json'
    winner='문제부터 좁혔습니다. 자료의 흐름을 다시 보니 다른 지점이 보였습니다. 그 부분만 고친 뒤 같은 오류가 없는지 확인했습니다.'
    loser='먼저 자료를 확인하고 대조했습니다. 또한 기준에 따라 검토하고 기록했습니다. 이를 통해 적극적으로 기여하겠습니다.'
    profile=record_preference(profile_path,winner_text=winner,loser_text=loser)
    assert preference_distance(winner,profile) < preference_distance(loser,profile)


def test_style_fingerprint_is_structural_not_content_copy():
    result=style_fingerprint('짧게 답했습니다. 다음 문장은 조금 더 길게 이유를 설명했습니다.')
    assert set(result) >= {'avg_sentence_chars','sentence_length_cv','bureaucratic_density'}
    assert all(isinstance(value,float) for value in result.values())
