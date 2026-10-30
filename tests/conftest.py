import pytest


def channel(cid, title, subs, views, videos, hidden=False):
    stats = {"viewCount": str(views), "videoCount": str(videos)}
    if hidden:
        stats["hiddenSubscriberCount"] = True
    else:
        stats["subscriberCount"] = str(subs)
    return {"id": cid, "title": title, "statistics": stats}


def payload(*channels):
    return {"items": list(channels)}


@pytest.fixture
def roster():
    return [
        {"channel_id": "UCa", "name": "Alpha", "youtube_handle": "@alpha", "instagram": "alpha_ig", "kind": "creator"},
        {"channel_id": "UCb", "name": "Beta", "youtube_handle": "@beta", "instagram": "beta_ig", "kind": "company"},
    ]
