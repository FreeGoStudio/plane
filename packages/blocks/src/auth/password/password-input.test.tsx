import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { TranslationProvider } from "@plane/i18n";
import { PasswordInput } from "./password-input";

it("supports password managers, long pasted values and revealing the password", () => {
  const onChange = vi.fn();
  const { rerender } = render(
    <TranslationProvider>
      <PasswordInput id="password" label="Password" value="" onChange={onChange} />
    </TranslationProvider>
  );
  const input = screen.getByLabelText("Password") as HTMLInputElement;
  expect(input.autocomplete).toBe("current-password");
  expect(input.hasAttribute("maxlength")).toBe(false);
  expect(fireEvent.paste(input)).toBe(true);
  const password = "  a long passphrase  ".repeat(10);
  fireEvent.change(input, { target: { value: password } });
  expect(onChange).toHaveBeenCalledWith(password);
  rerender(
    <TranslationProvider>
      <PasswordInput id="password" label="Password" value={password} onChange={onChange} autoComplete="new-password" />
    </TranslationProvider>
  );
  expect(input.autocomplete).toBe("new-password");
  fireEvent.click(screen.getByRole("button"));
  expect(input.type).toBe("text");
  expect(input.value).toBe(password);
});
