from parltopics.evaluate.scale import projection


def test_projection_scales_measured_pace_and_tokens():
    stats = {"affairs_per_min": 280.0, "records_per_affair": 1.0, "tokens_in_per_record": 1441, "tokens_out_per_record": 131}
    p = projection(stats, 336_000)
    assert p["hours"] == 20.0
    assert p["tokens_in_millions"] == 484 and p["tokens_out_millions"] == 44


def test_projection_counts_every_call_of_a_two_stage_scheme():
    stats = {"affairs_per_min": 80.0, "records_per_affair": 3.45, "tokens_in_per_record": 1018, "tokens_out_per_record": 119}
    assert projection(stats, 4800)["tokens_in_millions"] == round(4800 * 3.45 * 1018 / 1e6)
