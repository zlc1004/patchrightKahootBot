class BaseGameConfig:
    uri: str = ""
    code_input_xpath: str = ""
    submit_code_button_selector: str = ""
    nickname_input_xpath: str = ""
    submit_nickname_button_selector: str = ""

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
    pass

supported_games = {
    "kahoot": Kahoot,
    "myshortanswer": MyShortAnswer,
    "blooket": Blooket
}