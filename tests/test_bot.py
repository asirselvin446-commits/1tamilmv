"""Unit tests for 1TamilVT-TG Bot."""
import os
import tempfile
import pytest
from bot.config import Config
from bot.catalog import MovieCatalog

def test_config_validation():
    """Test that Config.validate passes when TOKEN is provided."""
    assert Config.TOKEN != ""
    assert Config.validate() is True

def test_authorized_users_parsing():
    """Test that authorized users include admin ID and all allowed user IDs."""
    auth_users = Config.get_authorized_users()
    assert isinstance(auth_users, set)
    # Check that parsed allowed users and admin are present
    assert 6406262636 in auth_users
    assert 7704762428 in auth_users
    assert 1505660795 in auth_users

def test_movie_catalog_operations():
    """Test MovieCatalog SQLite initialization, insertion, search, and cleanup."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = os.path.join(tmpdir, "test_catalog.db")
        catalog = MovieCatalog(db_path=test_db)

        assert catalog.get_total_count() == 0

        sample_movies = [
            {
                "title": "Leo (2023) Tamil Proper TRUE WEB-DL 1080p",
                "url": "https://1tamilmv.meme/index.php?/forums/topic/101-leo/",
                "quality": "1080p",
                "language": "Tamil",
                "source": "1TamilMV",
                "score": 2,
            },
            {
                "title": "Amaran (2024) Tamil HQ PreDVD 720p",
                "url": "https://1tamilmv.meme/index.php?/forums/topic/102-amaran/",
                "quality": "720p",
                "language": "Tamil",
                "source": "1TamilMV",
                "score": 1,
            },
            {
                "title": "DNA (2024) Malayalam WEB-DL 1080p",
                "url": "https://1tamilmv.meme/index.php?/forums/topic/103-dna/",
                "quality": "1080p",
                "language": "Malayalam",
                "source": "1TamilMV",
                "score": 2,
            }
        ]

        inserted = catalog.insert_movies(sample_movies)
        assert inserted == 3
        assert catalog.get_total_count() == 3

        # Test search
        results_leo = catalog.search("Leo")
        assert len(results_leo) == 1
        assert "Leo" in results_leo[0]["title"]

        results_multi = catalog.search("Amaran PreDVD")
        assert len(results_multi) == 1
        assert "Amaran" in results_multi[0]["title"]

        # Search for short query
        results_dna = catalog.search("DNA")
        assert len(results_dna) == 1
        assert "DNA" in results_dna[0]["title"]

        # Test non-matching query
        assert catalog.search("NonExistentMovieXYZ") == []
