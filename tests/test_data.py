from dcor_shared import sha256sum


def test_sha256sum(tmp_path):
    p = tmp_path / "test.txt"
    p.write_text("Sum this up!")
    ist = sha256sum(p)
    soll = "d00df55b97a60c78bbb137540e1b60647a5e6b216262a95ab96cafd4519bcf6a"
    assert ist == soll
