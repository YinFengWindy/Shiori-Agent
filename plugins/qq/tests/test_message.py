from plugins.qq.backend.channel.message import message_content


def test_structured_file_message_preserves_file_fields_missing_from_raw():
    assert (
        message_content(
            {
                "raw_message": "[文件]",
                "message": [
                    {"type": "text", "data": {"text": "[CQ:reply,id=99]"}},
                    {
                        "type": "file",
                        "data": {
                            "file_id": "id",
                            "file": "故事.txt",
                            "url": "https://x/a?a=1&b=2",
                        },
                    },
                ],
            }
        )
        == "&#91;CQ:reply,id=99&#93;[CQ:file,file_id=id,file=故事.txt,url=https://x/a?a=1&amp;b=2]"
    )


def test_raw_message_remains_compatible():
    assert (
        message_content({"raw_message": "[CQ:file,name=a.txt]"})
        == "[CQ:file,name=a.txt]"
    )
    assert message_content({"message": "hello"}) == "hello"
