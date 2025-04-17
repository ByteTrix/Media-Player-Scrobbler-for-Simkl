# Simkl Movie Tracker

A Python application that monitors the active window title on Windows, extracts the movie title, and updates the watch status on Simkl using its API.

## Features

- Detects the active window title.
- Parses the movie title using `guessit`.
- Searches for the movie on Simkl.
- Marks the movie as watched on Simkl.
- Uses Simkl's device authentication flow (requires user interaction on first run or if token expires).

## Requirements

- Python 3.x
- Dependencies listed in `requirements.txt`:
  - `requests`
  - `pygetwindow`
  - `guessit`
  - `python-dotenv`

## Installation

1.  Clone the repository:

    ```bash
    git clone https://github.com/kavinthangavel/simkl-movie-tracker.git 
    cd simkl-movie-tracker
    ```

2.  Install the dependencies:

    ```bash
    pip install -r requirements.txt
    ```

3.  Configure your Simkl API credentials:
    *   Copy the `.env.example` file to `.env`.
    *   Edit the `.env` file and add your `SIMKL_CLIENT_ID` and `SIMKL_CLIENT_SECRET` obtained from Simkl.
    *   You can optionally add a `SIMKL_ACCESS_TOKEN` if you already have one, otherwise the application will attempt to obtain one on the first run.

## Usage

Run the application from the project's root directory:

```bash
python main.py
```

**First Run / Authentication:**

If a valid `SIMKL_ACCESS_TOKEN` is not found in your `.env` file, the application will initiate the Simkl device authentication flow. You will be prompted to:

1.  Visit a URL provided by Simkl (e.g., `https://simkl.com/pin`).
2.  Enter a unique code displayed in the terminal.

The application will poll Simkl until you authorize it in your browser. Once authorized, it will store the obtained access token for future use (though currently, it only uses it for the session and recommends you manually add it to `.env`).

The application will then continuously check the active window title every 30 seconds and update the watch status on Simkl accordingly.

**Running in the Background (Windows):**

To run the script without keeping a terminal window open, you can use `pythonw.exe`:

```bash
pythonw.exe main.py
```

To stop it, you'll need to find the `pythonw.exe` process in Task Manager.
For more robust background execution (e.g., auto-restart), consider using Windows Task Scheduler.

## License

This project is licensed under the MIT License. *(Assuming MIT, update if different)*
