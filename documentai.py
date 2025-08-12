import sys
import os


# This makes sure the ai_chatbot_app package can be found.
# By adding the script's directory to the Python path, we make the script
# runnable from any location, and it helps tools like PyInstaller find modules.
# This is more robust than `sys.path.insert(0, '.')` as it does not depend
# on the current working directory.
script_dir = os.path.dirname(os.path.realpath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from ai_chatbot_app import main

if __name__ == '__main__':
    # Calling the main function from within this __name__ == '__main__' guard
    # is standard practice and works well with freezing tools like PyInstaller.
    main.main()
