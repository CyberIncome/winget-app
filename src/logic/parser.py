def parse_winget_upgrade(output):
    """
    Parses the tabular output from 'winget upgrade' command.
    Returns a list of dictionaries with Name, Id, Version, Available, and Source.
    """
    if not output or "No applicable update found" in output:
        return []

    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines or len(lines) < 2:
        return []

    # Find the header and the separator line (e.g., ----)
    header_line = ""
    separator_index = -1
    for i, line in enumerate(lines):
        if "Name" in line and "Id" in line and "Version" in line:
            header_line = line
            if i + 1 < len(lines) and lines[i+1].startswith("---"):
                separator_index = i + 1
            break
    
    if not header_line or separator_index == -1:
        return []

    # Calculate column start/end positions based on headers
    # Example headers: Name (0), Id (31), Version (62), Available (79), Source (96)
    # We find indices of these keywords
    col_names = ["Name", "Id", "Version", "Available", "Source"]
    indices = []
    for col in col_names:
        idx = header_line.find(col)
        indices.append(idx)
    
    # Append a large number for the last column's end
    indices.append(1000)

    results = []
    # Process lines after the separator
    for line in lines[separator_index + 1:]:
        row = {}
        for i in range(len(col_names)):
            start = indices[i]
            end = indices[i+1]
            # Capture the substring and strip whitespace
            value = line[start:end].strip() if start < len(line) else ""
            row[col_names[i]] = value
        
        if row.get("Name") and row.get("Id"):
            results.append(row)

    return results