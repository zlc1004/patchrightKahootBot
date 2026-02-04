class BaseGameConfig:
    uri: str = "" # The base URI for the game
    code_input_xpath: str = "" # The XPath for the game code input field
    submit_code_button_selector: str = "" # The selector for the submit code button
    nickname_input_xpath: str = "" # The XPath for the nickname input field
    submit_nickname_button_selector: str = "" # The selector for the submit nickname button
    require_secondary_code: bool = False # Whether a secondary code is required
    secondary_code_input_xpath: str = "" # The XPath for the secondary code input field
    secondary_code_submit_button_selector: str = "" # The selector for the secondary code submit button
    excute_additional_js: bool = False # Whether to execute additional JavaScript after joining
    excute_additional_js_wait_xpath: str = "" # The XPath to wait to be visible for before executing additional JS
    excute_additional_js_code: str = "" # Additional JavaScript to execute after joining

class Kahoot(BaseGameConfig):
    uri="https://kahoot.it"
    code_input_xpath="//*[@id=\"game-input\"]"
    submit_code_button_selector = "xpath=/html/body/div/div[1]/div/div/div[1]/div/div[2]/div[2]/main/div/form/button"
    nickname_input_xpath="//*[@id=\"nickname\"]"
    submit_nickname_button_selector = "xpath=/html/body/div/div[1]/div/div/div[1]/div/div[2]/main/div/form/button"

class MyShortAnswer(BaseGameConfig):
    uri="https://app.myshortanswer.com/join"
    code_input_xpath="//*[@id=\":r1:\"]"
    submit_code_button_selector = "xpath=/html/body/div/div/div/form/button"
    nickname_input_xpath="//*[@id=\"text-input-go-input\"]"
    submit_nickname_button_selector = "xpath=/html/body/div/form/div/div/div/button"

class Blooket(BaseGameConfig):
    uri="https://play.blooket.com/play"
    code_input_xpath="/html/body/main/div/form/div[1]/div/div/input"
    submit_code_button_selector = "xpath=/html/body/main/div/form/div[1]/div/button"
    nickname_input_xpath="/html/body/div/div/div/div[2]/div/form/div[2]/div[1]/input"
    submit_nickname_button_selector = "xpath=/html/body/div/div/div/div[2]/div/form/div[2]/div[2]"

class MagicSchoolAI(BaseGameConfig):
    uri="https://student.magicschool.ai/s/join"
    code_input_xpath="//*[@id=\"field2\"]"
    submit_code_button_selector = "xpath=//*[@id=\"field1\"]"
    nickname_input_xpath="//*[@id=\"field1\"]"
    submit_nickname_button_selector = "xpath=/html/body/div[2]/div/button"

supported_games = {
    "kahoot": Kahoot,
    "myshortanswer": MyShortAnswer,
    "blooket": Blooket,
    "magicschoolai": MagicSchoolAI
}