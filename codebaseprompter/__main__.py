import os
import argparse
from pathlib import Path
from typing import Any
import debugpy
import yaml
import xml.etree.ElementTree as ET
from xml.dom import minidom

# Global cache for loaded config to avoid repeated file I/O if called multiple times
_config_cache = None

def load_config(config_path: Path = Path("configs/config.yaml")) -> dict[str, dict[str, list[Any]]] | Any:
    """Loads configuration from a YAML file."""
    global _config_cache
    if _config_cache and _config_cache.get('path') == str(config_path):
        return _config_cache['data']

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        if not config_data or 'default_settings' not in config_data:
            print(f"Warning: Config file '{config_path}' is empty or missing 'default_settings'. Using empty defaults.")
            config_data = {'default_settings': {'source_extensions': [], 'omit_dirs': []}}

        _config_cache = {'path': str(config_path), 'data': config_data}
        return config_data
    except FileNotFoundError:
        print(f"Warning: Config file '{config_path}' not found. Using empty defaults.")
        return {'default_settings': {'source_extensions': [], 'omit_dirs': []}}
    except yaml.YAMLError as e:
        print(f"Error parsing YAML config file '{config_path}': {e}")
        return {'default_settings': {'source_extensions': [], 'omit_dirs': []}}


def get_source_extensions_and_filenames(config: dict[str, dict[str, list[Any]]]) -> tuple[set[str], set[str]]:
    """
    Extracts source extensions and specific filenames from config.
    Separates them because matching logic is different.
    """
    all_sources = config.get('default_settings', {}).get('source_extensions', [])
    extensions = {s.lower() for s in all_sources if s.startswith('.')}
    filenames = {s.lower() for s in all_sources if not s.startswith('.')}
    return extensions, filenames


def is_source_file(filename: str, configured_extensions: set[str], configured_filenames: set[str]) -> bool:
    """Checks if a filename is considered a source file based on loaded config."""
    fname_lower = filename.lower()
    if fname_lower in configured_filenames:
        return True
    return any(fname_lower.endswith(ext) for ext in configured_extensions)


def create_project_xml(
    project_dir: str,
    output_xml_file: str,
    additional_include: list[str] | None = None,
    cli_omit_dirs: list[str] | None = None,
    config_path: Path = Path("configs/config.yaml")
) -> None:
    """
    Creates an XML file from source files in a project directory.

    Args:
        project_dir (str): Path to the project's root directory.
        output_xml_file (str): Path to save the generated XML file.
        additional_include (list, optional): List of additional files to include.
        cli_omit_dirs (list, optional): List of directory names from CLI to omit.
        config_path (str): Path to the YAML configuration file.
    """
    config = load_config(config_path)
    configured_extensions, configured_filenames = get_source_extensions_and_filenames(config)
    configured_extensions.update({ext.lower() for ext in additional_include or []})
    
    default_omit_dirs_from_config = config.get('default_settings', {}).get('omit_dirs', [])
    
    # Combine omit_dirs: config defaults + CLI specified
    # CLI takes precedence if it needs to (though here we're just combining)
    # Normalizing to lowercase for case-insensitive matching
    final_omit_dirs_set = {d.lower() for d in default_omit_dirs_from_config}
    if cli_omit_dirs is not None:
        final_omit_dirs_set.update(d.lower() for d in cli_omit_dirs)

    project_root_abs = os.path.abspath(project_dir)
    if not os.path.isdir(project_root_abs):
        print(f"Error: Project directory '{project_dir}' not found.")
        return

    print(f"Scanning project: {project_root_abs}")
    print(f"Using config: {os.path.abspath(config_path)}")
    print(f"Omitting directories named (case-insensitive): {sorted(list(final_omit_dirs_set))}")
    print(f"Output XML: {output_xml_file}")

    # Create XML root using ElementTree
    xml_et_root = ET.Element("project")
    xml_et_root.set("name", os.path.basename(project_root_abs))

    file_count = 0

    for dirpath, dirnames, filenames_in_dir in os.walk(project_root_abs, topdown=True):
        # Pruning: Modify dirnames in-place to prevent os.walk from descending
        # Use the final_omit_dirs_set for efficient lookup
        dirnames[:] = [
            d for d in dirnames 
            if d.lower() not in final_omit_dirs_set and not any(d.lower().endswith(pattern.strip('*')) 
            for pattern in final_omit_dirs_set 
            if pattern.endswith('*'))
        ]

        for filename in filenames_in_dir:
            # Also check if the file itself matches a pattern in omit_dirs (e.g., *.log)
            # This is a simple check; more robust globbing could be added
            if filename.lower() in final_omit_dirs_set or \
               any(
                   filename.lower().endswith(pattern.strip('*')) 
                   for pattern in final_omit_dirs_set 
                   if pattern.endswith('*') and not pattern.startswith('*')
                ):
                continue

            if is_source_file(filename, configured_extensions, configured_filenames):
                full_path = os.path.join(dirpath, filename)
                relative_path = os.path.relpath(full_path, project_root_abs)
                relative_path_posix = relative_path.replace(os.sep, '/')

                print(f"  Adding: {relative_path_posix}")

                file_element = ET.SubElement(xml_et_root, "file")
                
                path_element = ET.SubElement(file_element, "path")
                path_element.text = relative_path_posix

                content_element = ET.SubElement(file_element, "content")
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        file_content = f.read()
                        # Set text for ElementTree. CDATA will be handled by minidom later.
                        content_element.text = file_content 
                    file_count += 1
                except Exception as e:
                    print(f"    Warning: Could not read file {relative_path_posix}: {e}")
                    content_element.text = f"Error reading file: {e}" # Store error as text

    # Convert ElementTree to string, then parse with minidom for pretty printing and CDATA
    rough_string = ET.tostring(xml_et_root, 'utf-8')
    
    try:
        reparsed_dom = minidom.parseString(rough_string)
    except Exception as e:
        print(f"Error: Failed to parse the intermediate XML string with minidom: {e}")
        print(
            "This might happen if file content itself contained malformed XML-like sequences that ET escaped, " +
            "but minidom had trouble re-parsing even the escaped version for CDATA conversion."
        )
        # Fallback: write the rough (but valid) XML string from ET
        try:
            with open(output_xml_file, 'wb') as f: # 'wb' for 'utf-8' encoded bytes
                f.write(rough_string)
            print(f"\nSuccessfully created XML (raw, non-pretty-printed): {output_xml_file} ({file_count} files included)")
        except IOError as ioe:
            print(f"Error: Could not write to output file {output_xml_file}: {ioe}")
        return

    # Ensure file content is within CDATA sections using minidom
    project_node_minidom = reparsed_dom.getElementsByTagName("project")[0]
    file_nodes_minidom = project_node_minidom.getElementsByTagName("file")

    for file_node in file_nodes_minidom:
        content_nodes = file_node.getElementsByTagName("content")
        if content_nodes:
            content_node_minidom = content_nodes[0]
            # Consolidate all child nodes of <content> (e.g. text, entities) into a single string
            text_parts = []
            for child in content_node_minidom.childNodes:
                if child.nodeType == child.TEXT_NODE:
                    text_parts.append(child.data)
                elif child.nodeType == child.CDATA_SECTION_NODE: # Should not happen yet, but good to handle
                    text_parts.append(child.data)
                # Potentially handle other node types if necessary, or log warning
            
            full_text_content = "".join(text_parts)

            # Remove old children
            while content_node_minidom.firstChild:
                content_node_minidom.removeChild(content_node_minidom.firstChild)
            
            # Add new CDATA section
            if full_text_content: # Only create CDATA if there's content
                cdata_node = reparsed_dom.createCDATASection(full_text_content)
                content_node_minidom.appendChild(cdata_node)
            # If content was empty (e.g. error message "Error reading file: ...") and we want it empty,
            # or if it was genuinely an empty file, this will result in <content></content>
            # If we want to put the error message *inside* CDATA, ensure full_text_content has it.
            # The current ET.SubElement sets text, so it should be there.
            elif content_node_minidom.getAttribute("error_placeholder"): # A bit of a hack if we set this attribute earlier
                content_node_minidom.appendChild(
                    reparsed_dom.createCDATASection(content_node_minidom.getAttribute("error_placeholder"))
                )

    try:
        with open(output_xml_file, 'w', encoding='utf-8') as f:
            # minidom's toprettyxml adds an XML declaration by default.
            # It also handles encoding.
            f.write(reparsed_dom.toprettyxml(indent="  ", encoding="utf-8").decode('utf-8'))
        print(f"\nSuccessfully created XML: {output_xml_file} ({file_count} files included)")
    except IOError as e:
        print(f"Error: Could not write to output file {output_xml_file}: {e}")
    except Exception as e:
        print(f"Error during final XML writing: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an XML representation of a project's source files.")
    parser.add_argument("project_dir", help="Path to the project directory.")
    parser.add_argument(
        "-o", "--output", default="project_sources.xml",
        help="Name of the output XML file (default: project_sources.xml)."
    )
    parser.add_argument(
        "-c", "--config", default="configs/config.yaml",
        help="Path to the YAML configuration file (default: config.yaml)."
    )
    parser.add_argument(
        "-a", "--additional_include", nargs='*', default=[],
        help="List of additional file extensions to include."
    )
    parser.add_argument(
        "--omit", nargs='*', default=[],
        help="List of additional directory/file names or patterns (*.log) to omit (e.g., temp_files old_code *.tmp)."
    )
    parser.add_argument(
        "--debug", action='store_true',
        help="Enable debug mode for verbose output."
    )
    
    args = parser.parse_args()

    if args.debug:
        print("Debug mode enabled.")
        debugpy.listen(("localhost", 5678))
        print("Debugging server started. Attach your debugger.")
        debugpy.wait_for_client()

    create_project_xml(args.project_dir, args.output, args.additional_include, args.omit, args.config)


if __name__ == "__main__":
    main()