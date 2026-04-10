## 2024-04-10 - Consistent CLI Visual Feedback and Logging
**Learning:** Raw `print` statements mixed with `rich.console` and poor silent error handling disrupt the user experience, making diagnostic outputs feel unprofessional and difficult to read.
**Action:** Consistently use `rich.console` for diagnostic/error messages in the CLI and properly log silent parsing errors (`json.JSONDecodeError`) as warnings to maintain both visual consistency and robust debugging capability without overwhelming standard output.
