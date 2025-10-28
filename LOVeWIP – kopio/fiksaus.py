#!/usr/bin/env python3
"""
Korjaa kaikki sqlite3.connect viittaukset app.py:ssä.
"""

def fix_app_py():
    with open('app.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    fixed_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Etsi "conn = db_manager.get_connection()"
        if 'conn = db_manager.get_connection()' in line:
            # Lisää rivi sellaisenaan
            fixed_lines.append(line)
            i += 1
            
            # Seuraavalla rivillä pitäisi olla "   try:" (väärä sisennys)
            if i < len(lines) and lines[i].strip() == 'try:':
                # Korjaa sisennys: poista ylimääräiset välilyönnit
                indent = len(lines[i]) - len(lines[i].lstrip())
                # Käytä samaa sisennystä kuin edellinen rivi
                prev_indent = len(line) - len(line.lstrip())
                fixed_lines.append(' ' * prev_indent + 'try:\n')
                i += 1
            
            continue
        
        fixed_lines.append(line)
        i += 1
    
    # Kirjoita takaisin
    with open('app.py', 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)
    
    print("✅ app.py korjattu!")

if __name__ == '__main__':
    fix_app_py()