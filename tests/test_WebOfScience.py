import pytest
import responses

from pubscraper.APIClasses import WebOfScience


@pytest.fixture
def test_skip_empty_name():
    """Test that providing an empty author name returns an empty result."""
    results = WebOfScience.search_multiple_authors([""])
    assert results == {}


def test_no_input():
    """Test that providing no input returns an empty result."""
    results = WebOfScience.search_multiple_authors([])
    assert results == {}


@responses.activate
def test_partial_empty_input():
    """Test that if one author is empty, it skips that author."""
    response_1 = responses.Response(
        method="GET",
        url="https://api.clarivate.com/api/wos/searches",
        status=200,
        json={
            "Data": {
                "Records": [
                    {
                        "Title": {"Title": "Sample Paper"},
                        "Source": {
                            "SourceTitle": "Test Journal",
                            "PublicationDate": "2023-01-15",
                        },
                        "Authors": [
                            {"LastName": "Albert", "FirstName": "A"},
                        ],
                        "DocumentType": "Article",
                        "Other": {
                            "Identifiers": [
                                {"Type": "Doi", "Value": "10.1234/sample"}
                            ]
                        }
                    }
                ]
            }
        },
    )
    responses.add(response_1)

    results = WebOfScience.search_multiple_authors(["Albert", ""])
    assert len(results) == 1


@responses.activate
def test_search_all_names():
    """Test searching for multiple author names returns expected number of results."""
    response_1 = responses.Response(
        method="GET",
        url="https://api.clarivate.com/api/wos/searches",
        status=200,
        json={
            "Data": {
                "Records": [
                    {
                        "Title": {"Title": "Paper 1"},
                        "Source": {
                            "SourceTitle": "Journal 1",
                            "PublicationDate": "2023-01-15",
                        },
                        "Authors": [
                            {"LastName": "Albert", "FirstName": "A"},
                        ],
                        "DocumentType": "Article",
                        "Other": {
                            "Identifiers": [
                                {"Type": "Doi", "Value": "10.1234/paper1"}
                            ]
                        }
                    }
                ]
            }
        },
    )
    responses.add(response_1)
    
    response_2 = responses.Response(
        method="GET",
        url="https://api.clarivate.com/api/wos/searches",
        status=200,
        json={
            "Data": {
                "Records": [
                    {
                        "Title": {"Title": "Paper 2"},
                        "Source": {
                            "SourceTitle": "Journal 2",
                            "PublicationDate": "2023-02-15",
                        },
                        "Authors": [
                            {"LastName": "Joe", "FirstName": "J"},
                        ],
                        "DocumentType": "Article",
                        "Other": {
                            "Identifiers": [
                                {"Type": "Doi", "Value": "10.1234/paper2"}
                            ]
                        }
                    }
                ]
            }
        },
    )
    responses.add(response_2)
    
    response_3 = responses.Response(
        method="GET",
        url="https://api.clarivate.com/api/wos/searches",
        status=200,
        json={
            "Data": {
                "Records": [
                    {
                        "Title": {"Title": "Paper 3"},
                        "Source": {
                            "SourceTitle": "Journal 3",
                            "PublicationDate": "2023-03-15",
                        },
                        "Authors": [
                            {"LastName": "Allen", "FirstName": "A"},
                        ],
                        "DocumentType": "Article",
                        "Other": {
                            "Identifiers": [
                                {"Type": "Doi", "Value": "10.1234/paper3"}
                            ]
                        }
                    }
                ]
            }
        },
    )
    responses.add(response_3)
    
    results = WebOfScience.search_multiple_authors(["Albert", "Joe", "Allen"])
    assert len(results) == 3


@responses.activate
def test_no_results():
    response_1 = responses.Response(
        method="GET",
        url="https://api.clarivate.com/api/wos/searches",
        status=200,
        json={"Data": {}},
    )
    responses.add(response_1)
    """Test that a name with no results returns an empty list for that name."""
    results = WebOfScience.search_multiple_authors(["John Smith"])
    assert results == {"John Smith": []}


@responses.activate
def test_middle_name_handling():
    """Test handling of author names with middle names."""
    response_1 = responses.Response(
        method="GET",
        url="https://api.clarivate.com/api/wos/searches",
        status=200,
        json={
            "Data": {
                "Records": [
                    {
                        "Title": {"Title": "Paper with Middle Name"},
                        "Source": {
                            "SourceTitle": "Journal of Middle Names",
                            "PublicationDate": "2023-04-15",
                        },
                        "Authors": [
                            {"LastName": "Smith", "FirstName": "John A"},
                        ],
                        "DocumentType": "Article",
                        "Other": {
                            "Identifiers": [
                                {"Type": "Doi", "Value": "10.1234/middle1"}
                            ]
                        }
                    }
                ]
            }
        },
    )
    responses.add(response_1)
    
    response_2 = responses.Response(
        method="GET",
        url="https://api.clarivate.com/api/wos/searches",
        status=200,
        json={
            "Data": {
                "Records": [
                    {
                        "Title": {"Title": "Paper with Multiple Middle Names"},
                        "Source": {
                            "SourceTitle": "Journal of Multiple Middle Names",
                            "PublicationDate": "2023-05-15",
                        },
                        "Authors": [
                            {"LastName": "Smith", "FirstName": "John Adam Bob"},
                        ],
                        "DocumentType": "Article",
                        "Other": {
                            "Identifiers": [
                                {"Type": "Doi", "Value": "10.1234/middle2"}
                            ]
                        }
                    }
                ]
            }
        },
    )
    responses.add(response_2)
    
    results = WebOfScience.search_multiple_authors(["John A Smith", "John Adam Bob Smith"])
    
    assert len(results) == 2
    assert "John A Smith" in results
    assert "John Adam Bob Smith" in results
    
    # Verify the correct papers were found
    assert results["John A Smith"][0]["title"] == "Paper with Middle Name"
    assert results["John Adam Bob Smith"][0]["title"] == "Paper with Multiple Middle Names"


@responses.activate
def test_limit_number_of_results():
    response_1 = responses.Response(
        method="GET",
        url="https://api.clarivate.com/api/wos/searches",
        status=200,
        json={
            "Data": {
                "Records": [
                    {
                        "Title": {"Title": "Paper 1"},
                        "Source": {
                            "SourceTitle": "Journal 1",
                            "PublicationDate": "2023-01-15",
                        },
                        "Authors": [
                            {"LastName": "Smith", "FirstName": "John"},
                        ],
                        "DocumentType": "Article",
                        "Other": {
                            "Identifiers": [
                                {"Type": "Doi", "Value": "10.1234/limit1"}
                            ]
                        }
                    },
                    {
                        "Title": {"Title": "Paper 2"},
                        "Source": {
                            "SourceTitle": "Journal 2",
                            "PublicationDate": "2023-02-15",
                        },
                        "Authors": [
                            {"LastName": "Smith", "FirstName": "John"},
                        ],
                        "DocumentType": "Article",
                        "Other": {
                            "Identifiers": [
                                {"Type": "Doi", "Value": "10.1234/limit2"}
                            ]
                        }
                    }
                ]
            }
        },
    )
    responses.add(response_1)

    """Test that the number of results is limited when specified."""
    results = WebOfScience.search_multiple_authors(["John Smith"], limit=2)
    assert len(results["John Smith"]) == 2


def test_should_fail():
    """Test that negative rows raises an exception."""
    wos = WebOfScience.WebOfScience()
    with pytest.raises(ValueError):
        wos.get_publications_by_author("John Smith", -1)


def test_bad_author_name():
    """Test handling of empty author name."""
    wos = WebOfScience.WebOfScience()
    result = wos.get_publications_by_author("")
    assert result is None


@responses.activate
def test_HTTP_failure():
    """Test handling of HTTP errors."""
    response_1 = responses.Response(
        method="GET",
        url="https://api.clarivate.com/api/wos/searches",
        status=500,
    )
    responses.add(response_1)
    
    results = WebOfScience.search_multiple_authors(["John Smith"])
    assert results["John Smith"] == []


@responses.activate
def test_malformed_response():
    """Test handling of malformed responses."""
    response_1 = responses.Response(
        method="GET",
        url="https://api.clarivate.com/api/wos/searches",
        status=200,
        json={
            "Data": {
                "Records": [
                    {
                        # Missing Title and other fields
                        "Source": {
                            "PublicationDate": "invalid-date",
                        },
                    }
                ]
            }
        },
    )
    responses.add(response_1)
    
    results = WebOfScience.search_multiple_authors(["John Smith"])
    # The WebOfScience class now checks for all required fields before adding a publication
    assert results["John Smith"] == []
