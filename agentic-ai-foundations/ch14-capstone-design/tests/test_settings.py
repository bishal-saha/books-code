from ch14.settings import Settings


def test_thinking_is_off_by_default_and_read_from_the_environment():
    assert Settings.from_env({}).model_thinking == "off"
    assert Settings.from_env({"MODEL_THINKING": "adaptive"}).model_thinking == "adaptive"
