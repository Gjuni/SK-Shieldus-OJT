from torch.distributions.constraints import boolean
import re

## 시스템 프롬프트 직접 언급
_SYSTEM_PROMPT_DIRECT_PATTERN = re.compile(
    r"(system\s*prompt|시스템\s*프롬프트|프롬프트\s*전부|전체\s*프롬프트|숨김\s*프롬프트|"
    r"개발자\s*메시지|developer\s*message|internal\s*prompt|정책\s*프롬프트)",
    re.IGNORECASE,
)

## 시스템 프롬프트 간접 언급
_SYSTEM_PROMPT_INDIRECT_PATTERN = re.compile(
    r"(너의\s*역할|너한테\s*주어진\s*지시|이전\s*지시|받은\s*지시|초기\s*설정|"
    r"너의\s*설정|내부\s*지침|숨겨진\s*지시|repeat\s*(your|the)\s*(system|initial)\s*(instruction|prompt|message)|"
    r"ignore\s*previous\s*instructions|이전\s*명령|처음\s*받은\s*명령|"
    r"위의\s*내용|print\s*above|above\s*instructions|지시\s*사항\s*알려|"
    r"configuration|설정\s*내용|original\s*instructions|원래\s*지시)",
    re.IGNORECASE,
)

## 유해 코드 차단
_BLOCKED_CODE_PATTERN = re.compile(
    r"(\bimport\s+sys\b|\bimport\s+os\b|\bfrom\s+os\s+import\b|"
    r"\bimport\s+subprocess\b|\bfrom\s+subprocess\s+import\b|"
    r"\bsocket\b|\brequests\b|\bshutil\b|\brm\s+-rf\b|"
    r"\bos\.system\b|\bos\.popen\b|\b__import__\b|"
    r"\bopen\s*\(|\beval\s*\(|\bexec\s*\(|"
    r"/proc/self|/etc/passwd|\.dockerenv)",
    re.IGNORECASE,
)

## 특수 토큰 차단
_GPT4O_SPECIAL_TOKENS_EXACT = re.compile(
    r"<\|(?:endoftext|im_start|im_end|fim_prefix|fim_middle|fim_suffix)\|>",
    re.IGNORECASE
)

## input 요소 검사
def check_input_prompt(text: str) -> boolean :
    ## 특수 토큰 정제
    text = _GPT4O_SPECIAL_TOKENS_EXACT.sub("", text)

    ## 시스템 프롬프트 직접 언급
    if _SYSTEM_PROMPT_DIRECT_PATTERN.search(text):
        return True

    ## 시스템 프롬프트 간접 언급
    if _SYSTEM_PROMPT_INDIRECT_PATTERN.search(text):
        return True

    ## 유해 코드 차단
    if _BLOCKED_CODE_PATTERN.search(text):
        return True
    return False

# output 요소 검사
def check_output_prompt(text: str) -> boolean :
    if _BLOCKED_CODE_PATTERN.search(text) :
        return True
    return False