"""Exceptions raised by the Configuration System."""


class ConfigError(Exception):
    """Base exception for all configuration-loading failures."""


class ConfigFileError(ConfigError):
    """Raised when the configuration file cannot be found, opened, or parsed as valid TOML.

    This is a distinct failure class from ConfigValidationError: it means the
    engine could not even read a candidate configuration, as opposed to
    reading one and finding it invalid.
    """


class ConfigValidationError(ConfigError):
    """Raised when a configuration file is syntactically valid TOML but fails
    schema or invariant validation.

    Carries every validation failure found in a single pass, not just the
    first one encountered, so a misconfigured deployment can be corrected in
    one pass instead of being re-run once per error.
    """

    def __init__(self, issues):
        self.issues = list(issues)
        message = "Configuration validation failed with {} issue(s):\n{}".format(
            len(self.issues),
            "\n".join(f"  - {issue}" for issue in self.issues),
        )
        super().__init__(message)
