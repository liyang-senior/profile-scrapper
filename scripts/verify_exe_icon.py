"""Exit 0 if the exe has Windows icon resources (RT_ICON + RT_GROUP_ICON)."""
import sys

import pefile

path = sys.argv[1]
pe = pefile.PE(path)
ids = [e.id for e in pe.DIRECTORY_ENTRY_RESOURCE.entries]
ok = 3 in ids and 14 in ids
print("icon_resources_ok", ok)
sys.exit(0 if ok else 1)
