package fixture

import (
	"fmt"
	"testing"
)

func TestGreet(t *testing.T) {
	if got := Greet("example"); got != "hello, example" {
		t.Fatalf("Greet() = %q", got)
	}
}

func ExampleGreet() {
	fmt.Println(Greet("example"))
	// Output: hello, example
}
