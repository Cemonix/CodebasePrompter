# CodebasePrompter

## Description
CodebasePrompter is a tool designed to convert a project's source files into an XML representation. This XML can then be used as a prompt for large language models (LLMs) to analyze and interact with the codebase. It supports customizable configurations for file types and directories to include or exclude.

## Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/Cemonix/CodebasePrompter.git
   ```
2. Navigate to the project directory:
   ```bash
   cd CodebasePrompter
   ```
3. Install the required dependencies using Poetry:
   ```bash
   poetry install
   ```

## Usage
1. Run the tool using Poetry:
   ```bash
   poetry run cbp <project_dir> -o <output_file>
   ```
   Replace `<project_dir>` with the path to the project you want to analyze and `<output_file>` with the desired name for the output XML file (default: `project_sources.xml`).

2. Optional arguments:
   - `-c`, `--config`: Path to a custom YAML configuration file (default: `configs/config.yaml`).
   - `-a`, `--additional_include`: Additional file extensions to include.
   - `--omit`: Additional directories or file patterns to exclude.

## Features
- Converts source files into an XML format for LLM prompts.
- Customizable file inclusion and exclusion rules via YAML configuration.
- Supports additional CLI options for flexibility.

## Contributing
Feel free to fork the repository and submit pull requests for new features or bug fixes.

## License
This project is licensed under the GNU General Public License v3. See the [LICENSE](LICENSE) file for details.
