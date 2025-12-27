import pytest
from src.logic.parser import parse_winget_upgrade

def test_parse_winget_upgrade_standard():
    sample_output = """Name                           Id                           Version          Available        Source
------------------------------------------------------------------------------------------------------
Google Chrome                  Google.Chrome                120.0.6099.110   120.0.6099.130   winget
Microsoft Visual Studio Code   Microsoft.VisualStudioCode   1.85.1           1.85.2           winget
"""
    results = parse_winget_upgrade(sample_output)
    
    assert len(results) == 2
    assert results[0]["Name"] == "Google Chrome"
    assert results[0]["Id"] == "Google.Chrome"
    assert results[0]["Version"] == "120.0.6099.110"
    assert results[0]["Available"] == "120.0.6099.130"
    assert results[0]["Source"] == "winget"
    
    assert results[1]["Id"] == "Microsoft.VisualStudioCode"

def test_parse_winget_upgrade_no_updates():
    sample_output = "No applicable update found."
    results = parse_winget_upgrade(sample_output)
    assert results == []

def test_parse_winget_upgrade_empty():
    results = parse_winget_upgrade("")
    assert results == []

def test_parse_winget_upgrade_with_unknown():
    # Example of how winget might show unknown versions
    sample_output = """Name                           Id                           Version          Available        Source
------------------------------------------------------------------------------------------------------
Some App                       Some.App                     unknown          1.2.3            winget
"""
    results = parse_winget_upgrade(sample_output)
    assert len(results) == 1
    assert results[0]["Version"] == "unknown"
