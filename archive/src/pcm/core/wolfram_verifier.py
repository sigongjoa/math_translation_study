import requests
import json
import logging
import re
from pathlib import Path

class WolframVerifier:
    """
    Verifies mathematical formulas and unit consistency 
    using LaTeX structural analysis and physical constant validation.
    """
    def __init__(self, app_id=None):
        self.app_id = app_id
        if self.app_id is None:
            logging.warning('WolframVerifier: app_id 없음, API 호출 스킵')
        
        self.api_url = "http://api.wolframalpha.com/v1/result"
        self.constants_path = Path("src/pcm/data/physical_constants.json")
        self._ensure_constants()

    def _ensure_constants(self):
        """Initializes a comprehensive list of physical constants (20+)."""
        recreate = False
        if not self.constants_path.exists():
            recreate = True
        else:
            try:
                with open(self.constants_path, "r", encoding="utf-8") as f:
                    current_constants = json.load(f)
                    # If any key is missing 'symbol' or we have fewer than 20, recreate
                    if len(current_constants) < 20 or not all('symbol' in v for v in current_constants.values()):
                        recreate = True
            except Exception:
                recreate = True

        if recreate:
            self.constants_path.parent.mkdir(parents=True, exist_ok=True)
            constants = {
                "c": {"value": 299792458, "unit": "m/s", "name": "speed of light", "symbol": "c"},
                "h": {"value": 6.62607015e-34, "unit": "J*s", "name": "Planck constant", "symbol": "h"},
                "G": {"value": 6.67430e-11, "unit": "m^3/(kg*s^2)", "name": "gravitational constant", "symbol": "G"},
                "hbar": {"value": 1.054571817e-34, "unit": "J*s", "name": "reduced Planck constant", "symbol": "\\hbar"},
                "kB": {"value": 1.380649e-23, "unit": "J/K", "name": "Boltzmann constant", "symbol": "k_B"},
                "epsilon0": {"value": 8.8541878128e-12, "unit": "F/m", "name": "vacuum permittivity", "symbol": "\\epsilon_0"},
                "mu0": {"value": 1.25663706212e-6, "unit": "N/A^2", "name": "vacuum permeability", "symbol": "\\mu_0"},
                "e": {"value": 1.602176634e-19, "unit": "C", "name": "elementary charge", "symbol": "e"},
                "me": {"value": 9.1093837015e-31, "unit": "kg", "name": "electron mass", "symbol": "m_e"},
                "mp": {"value": 1.67262192369e-27, "unit": "kg", "name": "proton mass", "symbol": "m_p"},
                "NA": {"value": 6.02214076e23, "unit": "mol^-1", "name": "Avogadro constant", "symbol": "N_A"},
                "R": {"value": 8.314462618, "unit": "J/(mol*K)", "name": "gas constant", "symbol": "R"},
                "sigma": {"value": 5.670374419e-8, "unit": "W/(m^2*K^4)", "name": "Stefan-Boltzmann constant", "symbol": "\\sigma"},
                "alpha": {"value": 7.2973525693e-3, "unit": "dimensionless", "name": "fine-structure constant", "symbol": "\\alpha"},
                "a0": {"value": 5.29177210903e-11, "unit": "m", "name": "Bohr radius", "symbol": "a_0"},
                "Ry": {"value": 13.605693122994, "unit": "eV", "name": "Rydberg energy", "symbol": "R_\\infty"},
                "eV": {"value": 1.602176634e-19, "unit": "J", "name": "electronvolt", "symbol": "eV"},
                "atm": {"value": 101325, "unit": "Pa", "name": "standard atmosphere", "symbol": "atm"},
                "cal": {"value": 4.184, "unit": "J", "name": "thermochemical calorie", "symbol": "cal"},
                "amu": {"value": 1.66053906660e-27, "unit": "kg", "name": "atomic mass unit", "symbol": "u"}
            }
            with open(self.constants_path, "w", encoding="utf-8") as f:
                json.dump(constants, f, indent=2, ensure_ascii=False)

    def verify_formula(self, formula_en, formula_ko):
        """Performs LaTeX structural verification between original and translation."""
        issues = []
        
        # Helper to check balance
        def check_balance(text, open_char, close_char):
            return text.count(open_char) == text.count(close_char)

        # (a) Braces balance
        if not check_balance(formula_ko, '{', '}'):
            issues.append("Braces { } are not balanced in translated formula.")
        
        # (c) Dollar signs balance
        if formula_ko.count('$') % 2 != 0:
            issues.append("Dollar signs $ are not paired in translated formula.")

        # (b) Key LaTeX commands presence
        commands = [r'\frac', r'\sqrt', r'\sum', r'\int', r'\partial', r'\nabla', r'\infty']
        for cmd in commands:
            count_en = formula_en.count(cmd)
            count_ko = formula_ko.count(cmd)
            if count_en != count_ko:
                issues.append(f"Command mismatch: '{cmd}' appears {count_en} times in English but {count_ko} times in Korean.")

        is_valid = len(issues) == 0
        return is_valid, issues

    def check_unit_consistency(self, text):
        """Checks for consistent usage of SI units and physical constants."""
        issues = []
        
        # Load constants
        with open(self.constants_path, "r", encoding="utf-8") as f:
            constants = json.load(f)

        # Pattern for number + unit (e.g., 3.0 x 10^8 m/s, 9.8 m/s^2)
        # Matches: 3, 3.14, 1e-10, 3x10^8, 3*10^8, 3 × 10^8
        num_pattern = r'[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?(?:\s*(?:x|×|\*)\s*10\^[-+]?\d+)?'
        unit_pattern = r'\s*([a-zA-Z]+(?:[\^/][0-9a-zA-Z^+-]+)*(?:\*[a-zA-Z]+)*)'
        
        matches = re.finditer(f'({num_pattern}){unit_pattern}', text)
        
        # Check detected units
        for match in matches:
            full_match = match.group(0)
            # Normalize scientific notation for comparison
            raw_val = match.group(1).replace('×', 'e').replace('x', 'e').replace('*10^', 'e').replace(' ', '')
            try:
                detected_value = float(raw_val)
            except ValueError:
                detected_value = None
            
            unit_str = match.group(2)
            
            # Non-SI detection (simple examples)
            non_si = {
                'cm': 'm', 'inch': 'm', 'mile': 'm', 'ft': 'm', 
                'erg': 'J', 'gauss': 'T', 'degree': 'rad'
            }
            for ns, si in non_si.items():
                if unit_str == ns or unit_str.startswith(ns + '/') or '/' + ns in unit_str:
                    issues.append(f"Non-SI unit '{ns}' detected in '{full_match}'. Consider using '{si}'.")

            # Value comparison against constants with same unit
            if detected_value is not None:
                for info in constants.values():
                    if info['unit'] == unit_str:
                        # Use a relative tolerance for comparison
                        if abs(detected_value - info['value']) / info['value'] > 0.01:
                            # Only flag if the unit is somewhat specific
                            if len(unit_str) > 2 or unit_str in ['m/s', 'J*s', 'F/m']:
                                issues.append(f"Detected value '{raw_val}' for unit '{unit_str}' differs significantly from constant '{info['name']}' ({info['value']}).")

        # Constant value verification
        for key, info in constants.items():
            # Use word boundaries for symbols to avoid matching 'c' in 'constant'
            # For LaTeX symbols like \hbar, we don't use \b at the start
            symbol = info['symbol']
            if symbol.startswith('\\'):
                symbol_pattern = re.escape(symbol)
            else:
                symbol_pattern = rf'\b{re.escape(symbol)}\b'
            
            name_pattern = rf'\b{re.escape(info["name"])}\b'

            if re.search(symbol_pattern, text) or re.search(name_pattern, text):
                # Find if the value of the constant appears in the text
                val_sci = f"{info['value']:.2e}"
                val_base = str(info['value'])
                
                # Check if units are present when the constant is mentioned
                if info['unit'] != "dimensionless" and info['unit'] not in text:
                    issues.append(f"Constant '{info['name']}' ({info['symbol']}) mentioned but its unit '{info['unit']}' is missing.")

        is_valid = len(issues) == 0
        return is_valid, issues
