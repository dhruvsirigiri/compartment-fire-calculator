"""A first test that only checks the project is wired up correctly:
pytest can find the tests folder and Python can import the fire_model package."""


def test_fire_model_package_imports():
    import fire_model

    assert fire_model.__doc__ is not None
