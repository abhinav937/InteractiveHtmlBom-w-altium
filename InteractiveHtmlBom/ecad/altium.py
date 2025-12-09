import os

import subprocess

import tempfile

import shutil

from .common import EcadParser


class AltiumParser(EcadParser):

    """

    Parser for Altium Designer .PcbDoc files.

    Uses altium2kicad converter to convert to KiCad format,

    then delegates to the KiCad parser.

    """



    def __init__(self, file_name, config, logger):

        super(AltiumParser, self).__init__(file_name, config, logger)

        self.converted_file = None

        self.kicad_parser = None



    def _check_perl(self):

        """Check if Perl is available."""

        try:

            result = subprocess.run(

                ['perl', '--version'],

                capture_output=True,

                text=True,

                timeout=5

            )

            return result.returncode == 0

        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):

            return False



    def _find_altium2kicad(self):

        """

        Try to find altium2kicad converter in common locations.

        Returns path to the converter directory or None.

        """

        # Check if Perl is available

        if not self._check_perl():

            self.logger.error(

                "Perl is required for altium2kicad conversion but not found.\n"

                "Please install Perl to use Altium .PcbDoc files."

            )

            return None



        # First, check if altium2kicad is included in the repository

        # Get the directory of this module (InteractiveHtmlBom/ecad)

        module_dir = os.path.dirname(os.path.abspath(__file__))

        # Go up to InteractiveHtmlBom, then to repo root

        repo_root = os.path.dirname(os.path.dirname(module_dir))

        repo_altium_dir = os.path.join(repo_root, 'altium2kicad')

        if os.path.exists(os.path.join(repo_altium_dir, 'convertpcb.pl')):

            return repo_altium_dir



        # Check if altium2kicad is in PATH

        try:

            result = subprocess.run(

                ['which', 'altium2kicad'],

                capture_output=True,

                text=True,

                timeout=5

            )

            if result.returncode == 0:

                # If it's in PATH, find the directory

                converter_path = os.path.dirname(result.stdout.strip())

                if os.path.exists(os.path.join(converter_path, 'convertpcb.pl')):

                    return converter_path

        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):

            pass



        # Check common installation locations

        common_paths = [

            os.path.expanduser('~/altium2kicad'),

            os.path.expanduser('~/github/altium2kicad'),

            '/usr/local/share/altium2kicad',

            '/opt/altium2kicad',

        ]



        for path in common_paths:

            if os.path.exists(os.path.join(path, 'convertpcb.pl')):

                return path



        # Check if it's in the same directory as the PCB file

        pcb_dir = os.path.dirname(os.path.abspath(self.file_name))

        if os.path.exists(os.path.join(pcb_dir, 'convertpcb.pl')):

            return pcb_dir

        

        # Check if altium2kicad subdirectory exists in PCB file directory

        altium_dir = os.path.join(pcb_dir, 'altium2kicad')

        if os.path.exists(os.path.join(altium_dir, 'convertpcb.pl')):

            return altium_dir



        # Check parent directories (up to 3 levels)

        current_dir = pcb_dir

        for _ in range(3):

            parent = os.path.dirname(current_dir)

            if parent == current_dir:

                break

            # Check in parent directory

            if os.path.exists(os.path.join(parent, 'convertpcb.pl')):

                return parent

            # Check altium2kicad subdirectory in parent

            altium_dir = os.path.join(parent, 'altium2kicad')

            if os.path.exists(os.path.join(altium_dir, 'convertpcb.pl')):

                return altium_dir

            current_dir = parent



        return None



    def _convert_to_kicad(self):

        """

        Convert .PcbDoc file to .kicad_pcb using altium2kicad.

        Returns path to converted file or None on error.

        """

        converter_dir = self._find_altium2kicad()

        if not converter_dir:

            self.logger.error(

                "altium2kicad converter not found.\n\n"

                "The altium2kicad converter should be included in this repository.\n"

                "If it's missing, please ensure the 'altium2kicad' directory exists\n"

                "in the repository root, or install it manually:\n"

                "  1. Install Perl (if not already installed)\n"

                "  2. Clone the repository:\n"

                "     git clone https://github.com/thesourcerer8/altium2kicad.git\n"

                "  3. Place it in the repository root as 'altium2kicad'\n\n"

                "Alternatively, manually convert your .PcbDoc to .kicad_pcb first,\n"

                "then use the generated .kicad_pcb file directly."

            )

            return None



        pcb_file = os.path.abspath(self.file_name)

        pcb_dir = os.path.dirname(pcb_file)

        pcb_basename = os.path.splitext(os.path.basename(pcb_file))[0]

        converted_file = os.path.join(pcb_dir, pcb_basename + '.kicad_pcb')



        # Check if converted file already exists and is newer

        if os.path.exists(converted_file):

            if os.path.getmtime(converted_file) >= os.path.getmtime(pcb_file):

                self.logger.info(

                    "Using existing converted file: {}".format(converted_file))

                return converted_file



        self.logger.info("Converting Altium .PcbDoc to KiCad format...")

        self.logger.info("Using altium2kicad from: {}".format(converter_dir))



        # Create a temporary directory for conversion

        temp_dir = tempfile.mkdtemp(prefix='altium2kicad_')

        try:

            # Copy PCB file to temp directory

            temp_pcb = os.path.join(temp_dir, os.path.basename(pcb_file))

            shutil.copy2(pcb_file, temp_pcb)



            # Change to temp directory for conversion

            original_cwd = os.getcwd()

            try:

                os.chdir(temp_dir)



                # Run unpack.pl

                unpack_script = os.path.join(converter_dir, 'unpack.pl')

                if not os.path.exists(unpack_script):

                    self.logger.error(

                        "unpack.pl not found in converter directory")

                    return None



                self.logger.info("Running unpack.pl...")

                result = subprocess.run(

                    ['perl', unpack_script],

                    capture_output=True,

                    text=True,

                    timeout=60

                )

                if result.returncode != 0:

                    self.logger.error(

                        "unpack.pl failed:\n{}".format(result.stderr))

                    return None



                # Run convertpcb.pl

                convert_script = os.path.join(converter_dir, 'convertpcb.pl')

                if not os.path.exists(convert_script):

                    self.logger.error(

                        "convertpcb.pl not found in converter directory")

                    return None



                self.logger.info("Running convertpcb.pl...")

                result = subprocess.run(

                    ['perl', convert_script],

                    capture_output=True,

                    text=True,

                    timeout=120

                )

                if result.returncode != 0:

                    self.logger.error(

                        "convertpcb.pl failed:\n{}".format(result.stderr))

                    if result.stdout:

                        self.logger.info("stdout: {}".format(result.stdout))

                    return None



                # Find the converted file

                converted_temp = os.path.join(

                    temp_dir, pcb_basename + '.kicad_pcb')

                if not os.path.exists(converted_temp):

                    # Try alternative naming

                    kicad_files = [

                        f for f in os.listdir(temp_dir)

                        if f.endswith('.kicad_pcb')

                    ]

                    if kicad_files:

                        converted_temp = os.path.join(temp_dir, kicad_files[0])

                    else:

                        self.logger.error(

                            "Converted .kicad_pcb file not found")

                        return None



                # Copy converted file to original directory

                shutil.copy2(converted_temp, converted_file)

                self.logger.info(

                    "Successfully converted to: {}".format(converted_file))

                return converted_file



            finally:

                os.chdir(original_cwd)



        except subprocess.TimeoutExpired:

            self.logger.error("Conversion timed out")

            return None

        except Exception as e:

            self.logger.error("Conversion failed: {}".format(str(e)))

            return None

        finally:

            # Clean up temp directory

            try:

                shutil.rmtree(temp_dir)

            except Exception:

                pass



    def parse(self):

        """

        Convert Altium file to KiCad format and parse using KiCad parser.

        """

        # Convert to KiCad format

        converted_file = self._convert_to_kicad()

        if not converted_file:

            return None, None



        self.converted_file = converted_file



        # Use KiCad parser on converted file

        try:

            # Lazy import to avoid requiring pcbnew for Altium files

            from .kicad import PcbnewParser

            self.kicad_parser = PcbnewParser(

                converted_file, self.config, self.logger)

            return self.kicad_parser.parse()

        except ImportError as e:

            self.logger.error(

                "KiCad Python API (pcbnew) is required to parse converted files.\n"

                "Please install KiCad or ensure pcbnew module is available.\n"

                "Error: {}".format(str(e)))

            return None, None

        except Exception as e:

            self.logger.error(

                "Failed to parse converted KiCad file: {}".format(str(e)))

            return None, None



    def get_extra_field_data(self, file_name):

        """

        Delegate to KiCad parser for extra field data.

        """

        if self.kicad_parser:

            return self.kicad_parser.get_extra_field_data(file_name)

        return super(AltiumParser, self).get_extra_field_data(file_name)



    def latest_extra_data(self, extra_dirs=None):

        """

        Delegate to KiCad parser for finding latest extra data.

        """

        if self.kicad_parser:

            return self.kicad_parser.latest_extra_data(extra_dirs)

        return super(AltiumParser, self).latest_extra_data(extra_dirs)



    def extra_data_file_filter(self):

        """

        Delegate to KiCad parser for extra data file filter.

        """

        if self.kicad_parser:

            return self.kicad_parser.extra_data_file_filter()

        return super(AltiumParser, self).extra_data_file_filter()

