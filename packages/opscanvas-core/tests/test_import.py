def test_package_exposes_version() -> None:
    import opscanvas_core

    assert isinstance(opscanvas_core.__version__, str)
    assert opscanvas_core.__version__
